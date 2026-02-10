import os
from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session as DBSession

from .db import get_db, engine, Base
from .models import User, Task
from .auth import login_or_register, get_current_user, COOKIE_NAME
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


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login_action(
    request: Request,
    name: str = Form(...),
    pin: str = Form(""),
    db: DBSession = Depends(get_db),
):
    pin_value = pin.strip() or None
    try:
        session = login_or_register(db, name.strip(), pin_value)
    except Exception as exc:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": str(exc.detail) if hasattr(exc, "detail") else str(exc)},
            status_code=401,
        )
    response = RedirectResponse("/tasks", status_code=303)
    response.set_cookie(COOKIE_NAME, session.token, httponly=True, max_age=7 * 86400, samesite="lax")
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def _require_user(request: Request, db: DBSession) -> User:
    user = get_current_user(request, db)
    if not user:
        raise RedirectResponse("/login", status_code=303)
    return user


@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse("/tasks", status_code=303)


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return templates.TemplateResponse(
        "tasks.html",
        {"request": request, "user": user, "tasks": tasks, "stream_url": STREAM_URL},
    )


@app.get("/tasks/partial", response_class=HTMLResponse)
async def tasks_partial(request: Request, db: DBSession = Depends(get_db)):
    tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    return templates.TemplateResponse("tasks_partial.html", {"request": request, "tasks": tasks})


@app.post("/tasks")
async def create_task(
    request: Request,
    text: str = Form(...),
    db: DBSession = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    task = Task(created_by_user_id=user.id, text=text.strip(), status="open")
    db.add(task)
    db.commit()
    await manager.broadcast_tasks_updated()
    return RedirectResponse("/tasks", status_code=303)


@app.post("/tasks/{task_id}/done")
async def mark_done(task_id: int, request: Request, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    task = db.query(Task).get(task_id)
    if task and task.status == "open":
        task.status = "done"
        db.commit()
        await manager.broadcast_tasks_updated()
    return RedirectResponse("/tasks", status_code=303)


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
