import secrets
import datetime
from typing import Optional
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session as DBSession
from passlib.hash import bcrypt

from .models import User, Session

SESSION_DURATION_DAYS = 7
COOKIE_NAME = "session_token"


def hash_pin(pin: str) -> str:
    return bcrypt.hash(pin)


def verify_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.verify(pin, pin_hash)


def login_or_register(db: DBSession, name: str, pin: Optional[str]) -> Session:
    """Authenticate existing user or create new one. Returns a Session."""
    user = db.query(User).filter(User.name == name).first()

    if user is None:
        # Register
        user = User(name=name, pin_hash=hash_pin(pin) if pin else None)
        db.add(user)
        db.flush()
    else:
        # Existing user – check PIN
        if user.pin_hash:
            if not pin or not verify_pin(pin, user.pin_hash):
                raise HTTPException(status_code=401, detail="Falsche PIN")
        # If user has no pin_hash, any (or no) PIN is accepted

    token = secrets.token_hex(32)
    session = Session(
        user_id=user.id,
        token=token,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=SESSION_DURATION_DAYS),
    )
    db.add(session)
    db.commit()
    return session


def get_current_user(request: Request, db: DBSession) -> Optional[User]:
    """Return the logged-in User or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    session = (
        db.query(Session)
        .filter(Session.token == token, Session.expires_at > datetime.datetime.utcnow())
        .first()
    )
    if not session:
        return None
    return session.user
