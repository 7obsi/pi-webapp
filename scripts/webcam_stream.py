#!/usr/bin/env python3
"""Simple MJPEG webcam streamer on port 8081.

Replaces mjpeg-streamer for local development on macOS/Linux.
Open http://localhost:8081 in a browser to see the stream.
"""
import cv2
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

PORT = 8081
QUALITY = 70  # JPEG quality (0-100)

lock = threading.Lock()
frame_bytes = b""


def capture_loop():
    global frame_bytes
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open webcam")
        return
    print(f"Webcam opened, streaming on http://0.0.0.0:{PORT}")
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, QUALITY])
        if ret:
            with lock:
                frame_bytes = jpeg.tobytes()


class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            while True:
                with lock:
                    data = frame_bytes
                if not data:
                    continue
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(data)}\r\n\r\n".encode())
                self.wfile.write(data)
                self.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        pass  # suppress per-request logs


if __name__ == "__main__":
    thread = threading.Thread(target=capture_loop, daemon=True)
    thread.start()
    server = HTTPServer(("0.0.0.0", PORT), MJPEGHandler)
    print(f"MJPEG server listening on http://0.0.0.0:{PORT}")
    server.serve_forever()
