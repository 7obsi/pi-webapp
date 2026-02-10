#!/usr/bin/env python3
"""Create all database tables."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import engine, Base
from app.models import User, Session, Task  # noqa: F401 – register models

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print(f"Database created at {engine.url}")
