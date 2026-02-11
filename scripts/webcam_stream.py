#!/usr/bin/env python3
"""Live view streamer on port 8081.

Auto-detects camera source:
  1. gphoto2 (Sony/Nikon via USB in PC Remote mode)
  2. ffmpeg + V4L2 webcam (/dev/video0)
"""
import datetime
import os
import subprocess
import shutil
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 8081
DEVICE = "/dev/video0"
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "/recordings")
RECORD_FPS = int(os.environ.get("RECORD_FPS", "15"))

lock = threading.Lock()
frame_bytes = b""

recording_lock = threading.Lock()
recording_active = False
recording_proc = None
recording_thread = None
recording_path = None


def _sanitize_label(value: str) -> str:
    value = value.strip().lower()
    cleaned = []
    for ch in value:
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in (" ", "-", "_"):
            cleaned.append("_")
    result = "".join(cleaned).strip("_")
    return result or "unknown"


def _record_loop():
    global recording_active, recording_proc
    interval = 1.0 / max(RECORD_FPS, 1)
    while True:
        with recording_lock:
            active = recording_active
            proc = recording_proc
        if not active or proc is None or proc.poll() is not None:
            break
        with lock:
            data = frame_bytes
        if data:
            try:
                proc.stdin.write(data)
                proc.stdin.flush()
            except Exception:
                break
        time.sleep(interval)
    try:
        if recording_proc and recording_proc.stdin:
            recording_proc.stdin.close()
    except Exception:
        pass


def start_recording(task: str, names: str) -> tuple[bool, str | None]:
    global recording_active, recording_proc, recording_thread, recording_path
    with recording_lock:
        if recording_active and recording_proc and recording_proc.poll() is None:
            return False, recording_path
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_task = _sanitize_label(task)
        safe_names = _sanitize_label(names)
        filename = f"{ts}__{safe_names}__{safe_task}.mp4"
        recording_path = os.path.join(RECORDINGS_DIR, filename)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "mjpeg",
            "-r",
            str(RECORD_FPS),
            "-i",
            "pipe:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            recording_path,
        ]
        try:
            recording_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        except Exception:
            recording_proc = None
            recording_active = False
            return False, None
        recording_active = True
        recording_thread = threading.Thread(target=_record_loop, daemon=True)
        recording_thread.start()
        return True, recording_path


def stop_recording() -> str | None:
    global recording_active, recording_proc, recording_thread, recording_path
    with recording_lock:
        if not recording_active:
            return recording_path
        recording_active = False
        proc = recording_proc
        path = recording_path
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    recording_proc = None
    recording_thread = None
    return path


def detect_gphoto2_camera():
    if not shutil.which("gphoto2"):
        return False
    try:
        result = subprocess.run(
            ["gphoto2", "--auto-detect"],
            capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.strip().split("\n")
        # First two lines are header, cameras follow
        return len(lines) > 2
    except Exception:
        return False


def capture_loop_gphoto2():
    global frame_bytes
    print("Using gphoto2 capture...", flush=True)
    while True:
        try:
            result = subprocess.run(
                ["gphoto2", "--capture-preview", "--stdout"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0 and len(result.stdout) > 100:
                with lock:
                    frame_bytes = result.stdout
            else:
                time.sleep(0.5)
        except subprocess.TimeoutExpired:
            time.sleep(0.5)
        except Exception as e:
            print(f"gphoto2 error: {e}", flush=True)
            time.sleep(1)


def capture_loop_ffmpeg():
    global frame_bytes
    cmd = [
        "ffmpeg",
        "-f", "v4l2",
        "-input_format", "mjpeg",
        "-video_size", "640x480",
        "-framerate", "15",
        "-i", DEVICE,
        "-c:v", "copy",
        "-f", "mjpeg",
        "pipe:1",
    ]
    print(f"Using ffmpeg webcam: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    buf = b""
    while True:
        chunk = proc.stdout.read(4096)
        if not chunk:
            stderr = proc.stderr.read().decode(errors="replace")
            print(f"ffmpeg exited (rc={proc.wait()}). stderr:\n{stderr}", flush=True)
            break
        buf += chunk
        while True:
            soi = buf.find(b"\xff\xd8")
            if soi == -1:
                buf = b""
                break
            eoi = buf.find(b"\xff\xd9", soi + 2)
            if eoi == -1:
                buf = buf[soi:]
                break
            frame = buf[soi:eoi + 2]
            buf = buf[eoi + 2:]
            with lock:
                frame_bytes = frame


class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/record/start":
            params = parse_qs(parsed.query)
            task = params.get("task", ["unknown"])[0]
            names = params.get("names", ["unknown"])[0]
            ok, path = start_recording(task, names)
            self.send_response(200 if ok else 409)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write((path or "").encode())
            return
        if parsed.path == "/record/stop":
            path = stop_recording()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write((path or "").encode())
            return
        with lock:
            data = frame_bytes
        if not data:
            self.send_response(503)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    if detect_gphoto2_camera():
        target = capture_loop_gphoto2
    else:
        target = capture_loop_ffmpeg

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    server = HTTPServer(("0.0.0.0", PORT), StreamHandler)
    print(f"Stream server listening on http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever()
