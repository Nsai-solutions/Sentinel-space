"""SQLite database connection and session management."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# On Vercel, use /tmp (ephemeral writable dir). Locally use backend/data/.
if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp") / "sentinelspace.db"
else:
    DB_PATH = Path(__file__).parent.parent / "data" / "sentinelspace.db"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)


# Enable WAL mode for better concurrent read performance
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Session:
    """Dependency for FastAPI route injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    from database import models  # noqa: F401 — ensure ORM models are registered
    Base.metadata.create_all(bind=engine)
