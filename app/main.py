import os
import random
from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session as DBSession

from .db import get_db, engine, Base
from .models import Task, Attendee
from .ws import manager

# Create tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# In production behind Caddy: "/stream"
# For local dev: "http://localhost:8081"
STREAM_URL = os.environ.get("STREAM_URL", "http://localhost:8081")

# Display state (in-memory, resets on restart)
kisscam_state = {
    "active": False,
    "current_task": None,
    "drawn": None,          # [name1, name2] after draw
    "task_running": False,   # True when task is shown on TV
    "last_drawn": [],        # last 2 drawn names, excluded from next draw
}


# ---------------------------------------------------------------------------
# Kiss Cam
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse("/admin", status_code=303)


@app.get("/kisscam", response_class=HTMLResponse)
async def kisscam_page(request: Request):
    return templates.TemplateResponse(
        "kisscam.html",
        {"request": request, "stream_url": STREAM_URL},
    )


@app.get("/kisscam/state")
async def kisscam_get_state():
    return JSONResponse(kisscam_state)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, db: DBSession = Depends(get_db)):
    attendees = db.query(Attendee).order_by(Attendee.name).all()
    unused_count = db.query(Task).filter(Task.status == "open").count()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "active": kisscam_state["active"],
            "current_task": kisscam_state["current_task"],
            "drawn": kisscam_state["drawn"],
            "task_running": kisscam_state["task_running"],
            "unused_count": unused_count,
            "attendees": attendees,
        },
    )


@app.post("/admin/toggle")
async def admin_toggle():
    kisscam_state["active"] = not kisscam_state["active"]
    await manager.broadcast_kisscam_state(kisscam_state["active"])
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/pick-task")
async def pick_task(db: DBSession = Depends(get_db)):
    tasks = db.query(Task).filter(Task.status == "open").all()
    if tasks:
        task = random.choice(tasks)
        task.status = "used"
        db.commit()
        kisscam_state["current_task"] = task.text
        await manager.broadcast_task_selected(task.text)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/clear-task")
async def clear_task():
    kisscam_state["current_task"] = None
    kisscam_state["drawn"] = None
    kisscam_state["task_running"] = False
    await manager.broadcast_stop_task()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/draw")
async def draw_attendees(db: DBSession = Depends(get_db)):
    attendees = db.query(Attendee).all()
    if len(attendees) >= 2:
        all_names = [a.name for a in attendees]
        # Exclude last drawn pair if possible
        eligible = [a for a in attendees if a.name not in kisscam_state["last_drawn"]]
        if len(eligible) < 2:
            eligible = list(attendees)
        selected = random.sample(eligible, 2)
        sel_names = [selected[0].name, selected[1].name]
        kisscam_state["drawn"] = sel_names
        kisscam_state["last_drawn"] = sel_names
        kisscam_state["task_running"] = False
        await manager.broadcast_draw(all_names, sel_names)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/start-task")
async def start_task():
    if kisscam_state["current_task"] and kisscam_state["drawn"]:
        kisscam_state["task_running"] = True
        await manager.broadcast_start_task(
            kisscam_state["current_task"],
            kisscam_state["drawn"],
        )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/stop-task")
async def stop_task():
    kisscam_state["task_running"] = False
    kisscam_state["drawn"] = None
    kisscam_state["current_task"] = None
    await manager.broadcast_stop_task()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/attendees")
async def add_attendee(name: str = Form(...), db: DBSession = Depends(get_db)):
    db.add(Attendee(name=name.strip()))
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/attendees/{attendee_id}/delete")
async def delete_attendee(attendee_id: int, db: DBSession = Depends(get_db)):
    attendee = db.query(Attendee).get(attendee_id)
    if attendee:
        db.delete(attendee)
        db.commit()
    return RedirectResponse("/admin", status_code=303)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@app.get("/tasks/add", response_class=HTMLResponse)
async def tasks_add_page(request: Request):
    saved = request.query_params.get("saved")
    return templates.TemplateResponse(
        "tasks_add.html",
        {"request": request, "saved": saved},
    )


@app.post("/tasks/add")
async def tasks_add_action(text: str = Form(...), db: DBSession = Depends(get_db)):
    db.add(Task(text=text.strip(), status="open"))
    db.commit()
    await manager.broadcast_tasks_updated()
    return RedirectResponse("/tasks/add?saved=1", status_code=303)


@app.get("/tasks/manage", response_class=HTMLResponse)
async def tasks_manage_page(request: Request, db: DBSession = Depends(get_db)):
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return templates.TemplateResponse(
        "tasks_manage.html",
        {"request": request, "tasks": tasks},
    )


@app.post("/tasks/{task_id}/delete")
async def delete_task(task_id: int, db: DBSession = Depends(get_db)):
    task = db.query(Task).get(task_id)
    if task:
        db.delete(task)
        db.commit()
        await manager.broadcast_tasks_updated()
    return RedirectResponse("/tasks/manage", status_code=303)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(ws)
