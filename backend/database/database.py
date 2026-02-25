"""SQLite database connection and session management."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event, text
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
    _migrate_columns()


def _migrate_columns():
    """Add new columns/tables to existing databases.

    SQLAlchemy create_all() creates new tables but won't add columns to
    existing ones.  We use ALTER TABLE wrapped in try/except — SQLite
    raises an error if the column already exists, which we silently ignore.

    We also include CREATE TABLE IF NOT EXISTS for tables added after the
    initial release, as a safety net in case create_all() somehow missed them
    (e.g. persistent DB on Render from a prior deployment).
    """
    column_migrations = [
        "ALTER TABLE assets ADD COLUMN screening_window_days FLOAT DEFAULT 7.0",
        "ALTER TABLE assets ADD COLUMN screening_threshold_km FLOAT DEFAULT 25.0",
        "ALTER TABLE assets ADD COLUMN auto_screen BOOLEAN DEFAULT 1",
    ]

    table_migrations = [
        """CREATE TABLE IF NOT EXISTS notification_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email VARCHAR(255),
            email_enabled BOOLEAN DEFAULT 0,
            notify_critical BOOLEAN DEFAULT 1,
            notify_high BOOLEAN DEFAULT 1,
            notify_moderate BOOLEAN DEFAULT 0,
            notify_low BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
            updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP)
        )""",
        """CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(128) NOT NULL,
            key_hash VARCHAR(64) NOT NULL UNIQUE,
            key_prefix VARCHAR(8) NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
            last_used_at DATETIME
        )""",
        """CREATE TABLE IF NOT EXISTS conjunction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_asset_id INTEGER NOT NULL REFERENCES assets(id),
            secondary_norad_id INTEGER NOT NULL,
            secondary_name VARCHAR(128),
            tca DATETIME NOT NULL,
            miss_distance_m FLOAT NOT NULL,
            radial_m FLOAT,
            in_track_m FLOAT,
            cross_track_m FLOAT,
            relative_velocity_kms FLOAT,
            collision_probability FLOAT,
            threat_level VARCHAR(8),
            screening_job_id INTEGER REFERENCES screening_jobs(id),
            screened_at DATETIME DEFAULT (CURRENT_TIMESTAMP)
        )""",
    ]

    with engine.connect() as conn:
        for sql in table_migrations + column_migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # Table/column already exists
