#!/usr/bin/env python3
"""Live view streamer on port 8081.

Auto-detects camera source:
  1. gphoto2 (Sony/Nikon via USB in PC Remote mode)
  2. ffmpeg + V4L2 webcam (/dev/video0)
"""
import subprocess
import shutil
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = 8081
DEVICE = "/dev/video0"

lock = threading.Lock()
frame_bytes = b""


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
