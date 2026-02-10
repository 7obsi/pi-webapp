# Pi Webapp

Aufgaben-App mit Live-Webcam-Stream, Mehrbenutzer-Login und Echtzeit-Updates per WebSocket. Laeuft auf einem Raspberry Pi im lokalen Netzwerk.

## Features

- Webcam-Livestream im Browser
- Login mit Name + optionaler PIN (automatische Registrierung)
- Aufgaben erstellen und abhaken
- Live-Updates auf allen Geraeten per WebSocket
- Alles per Docker in einem Befehl startbar

## Voraussetzungen auf dem Raspberry Pi

- Raspberry Pi OS (64-bit empfohlen)
- Docker und Docker Compose installiert
- USB-Webcam oder offizielle Pi-Kamera

### Docker installieren

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Danach neu einloggen oder reboot
```

### Pi-Kamera aktivieren (nur bei Ribbon-Kabel-Kamera)

```bash
sudo raspi-config
# → Interface Options → Camera → Enable
sudo reboot
```

Bei einer USB-Webcam ist dieser Schritt nicht noetig.

## Installation

### 1. Projekt auf den Pi kopieren

Vom Laptop aus:

```bash
scp -r ~/Documents/private_workspace/pi-webapp pi@<pi-ip>:~/pi-webapp
```

`<pi-ip>` durch die IP-Adresse des Pi ersetzen (z.B. `192.168.1.50`).

### 2. Webcam anschliessen

USB-Webcam einstecken und pruefen:

```bash
ls /dev/video0
```

Wenn die Datei existiert, ist die Kamera erkannt.

### 3. App starten

```bash
cd ~/pi-webapp
docker compose up -d
```

Beim ersten Start wird das Docker-Image gebaut (dauert ein paar Minuten).

### 4. Im Browser oeffnen

Von jedem Geraet im selben Netzwerk:

```
http://<pi-ip>
```

## Nuetzliche Befehle

```bash
# Logs anzeigen
docker compose logs -f

# App stoppen
docker compose down

# App neu bauen (nach Code-Aenderungen)
docker compose up -d --build
```

## Lokale Entwicklung (ohne Docker)

Auf dem Laptop zum Testen:

**Terminal 1 — Webcam-Stream:**

```bash
cd pi-webapp
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install opencv-python
python scripts/webcam_stream.py
```

**Terminal 2 — Web-App:**

```bash
cd pi-webapp
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Dann im Browser: `http://localhost:8000`

## Architektur

| Service | Port | Beschreibung |
|---------|------|--------------|
| web | 8000 | FastAPI App (Jinja2 + HTMX) |
| stream | 8081 | MJPEG Webcam-Stream |
| caddy | 80 | Reverse Proxy (buendelt alles) |
