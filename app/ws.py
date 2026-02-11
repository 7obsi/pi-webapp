import json
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast_tasks_updated(self):
        message = json.dumps({"type": "tasks_updated"})
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                self.active.remove(ws)

    async def broadcast_kisscam_state(self, active: bool):
        message = json.dumps({"type": "kisscam_state", "active": active})
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                self.active.remove(ws)

    async def broadcast_task_selected(self, task_text):
        message = json.dumps({"type": "task_selected", "text": task_text})
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                self.active.remove(ws)

    async def broadcast_draw(self, all_names, selected):
        message = json.dumps({"type": "draw_attendees", "all_names": all_names, "selected": selected})
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                self.active.remove(ws)

    async def broadcast_start_task(self, task_text, names):
        message = json.dumps({"type": "start_task", "task": task_text, "names": names})
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                self.active.remove(ws)

    async def broadcast_stop_task(self):
        message = json.dumps({"type": "stop_task"})
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except Exception:
                self.active.remove(ws)


manager = ConnectionManager()
