# Pi Webapp

Task app with live webcam stream, multi-user login, and realtime updates via WebSocket. Runs on a Raspberry Pi in the local network.

## Features

- Live webcam stream in the browser
- Login with name + optional PIN (auto-registration)
- Create and complete tasks
- Live updates on all devices via WebSocket
- Runs via Docker in one command
- Optional task video recording (saved on the Pi)
- Warm-up countdown before tasks start
- No-repeat cooldown for attendee draws

## Requirements on the Raspberry Pi

- Raspberry Pi OS (64-bit recommended)
- Docker and Docker Compose installed
- USB webcam or official Pi camera

### Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in or reboot
```

### Enable Pi camera (only for ribbon cable camera)

```bash
sudo raspi-config
# -> Interface Options -> Camera -> Enable
sudo reboot
```

If you use a USB webcam, this step is not required.

## Installation

### 1. Copy the project to the Pi

From your laptop:

```bash
scp -r ~/Documents/private_workspace/pi-webapp pi@<pi-ip>:~/pi-webapp
```

Replace `<pi-ip>` with your Pi's IP address (e.g. `192.168.1.50`).

### 2. Connect the webcam

Plug in the USB webcam and verify:

```bash
ls /dev/video0
```

If the file exists, the camera is detected.

### 3. Start the app

```bash
cd ~/pi-webapp
docker compose up -d
```

The first build takes a few minutes.

### 4. Open in the browser

From any device on the same network:

```
http://<pi-ip>
```

## Useful commands

```bash
# View logs
docker compose logs -f

# Stop the app
docker compose down

# Rebuild (after code changes)
docker compose up -d --build
```

## Recording (Task Videos)

When a task starts, recording begins; when it ends, recording stops.
Videos are saved on the Pi under `recordings/` with timestamps, names, and task text in the filename.
Recording can be enabled/disabled in the Admin page and the setting persists across restarts.

## Countdown + No-repeat cooldown

When a task starts, the kisscam shows a 3-2-1 countdown before the task overlay appears.
You can set how many rounds an attendee is excluded from re-draw in the Admin page.

## Local Development (without Docker)

On your laptop for testing:

**Terminal 1 — Webcam stream:**

```bash
cd pi-webapp
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install opencv-python
python scripts/webcam_stream.py
```

**Terminal 2 — Web app:**

```bash
cd pi-webapp
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open: `http://localhost:8000`

## Architecture

| Service | Port | Description |
|---------|------|-------------|
| web | 8000 | FastAPI app (Jinja2 + HTMX) |
| stream | 8081 | MJPEG webcam stream |
| caddy | 80 | Reverse proxy (bundles everything) |
