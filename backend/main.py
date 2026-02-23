"""SentinelSpace — FastAPI Backend Entry Point."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend package is importable
BACKEND_ROOT = Path(__file__).parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database.database import init_db
from routers import assets, tle, screening, conjunctions, maneuvers, environment, alerts, reports, orbit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("SentinelSpace starting up")
    init_db()
    logger.info("Database initialized")

    # Pre-load TLE catalog in background
    from services.tle_catalog import catalog_service
    catalog_service.initialize()

    # Seed default assets if DB is empty (handles Vercel cold starts)
    from database.database import SessionLocal
    from database.models import Asset

    db = SessionLocal()
    try:
        if db.query(Asset).count() == 0:
            logger.info("Empty database detected, seeding default assets...")
            default_norad_ids = [25544, 33591, 41866]  # ISS, NOAA 19, GOES 16
            for nid in default_norad_ids:
                try:
                    tle = catalog_service.get_tle(nid)
                    if not tle:
                        continue
                    existing = db.query(Asset).filter(Asset.norad_id == nid).first()
                    if existing:
                        continue
                    orbit_type = None
                    try:
                        from core.propagator import OrbitalPropagator
                        prop = OrbitalPropagator(tle)
                        elements = prop.get_orbital_elements(datetime.utcnow())
                        orbit_type = elements.orbit_type
                    except Exception:
                        pass
                    asset = Asset(
                        norad_id=tle.catalog_number,
                        name=tle.name,
                        tle_line1=tle.line1,
                        tle_line2=tle.line2,
                        tle_epoch=tle.epoch_datetime,
                        orbit_type=orbit_type,
                    )
                    db.add(asset)
                    db.commit()
                    logger.info("Seeded asset: %s (NORAD %d)", tle.name, nid)
                except Exception as e:
                    logger.warning("Failed to seed NORAD %d: %s", nid, e)
                    db.rollback()
    finally:
        db.close()

    yield

    logger.info("SentinelSpace shutting down")


app = FastAPI(
    title="SentinelSpace",
    description="Space Debris Threat Assessment Platform",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://sentinel-space-six.vercel.app",
]

# Add Vercel deployment URL if available
_vercel_url = os.environ.get("VERCEL_URL")
if _vercel_url:
    _cors_origins.append(f"https://{_vercel_url}")

# Add custom frontend URL if configured
_frontend_url = os.environ.get("FRONTEND_URL")
if _frontend_url:
    _cors_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://sentinel-space.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(assets.router, prefix="/api/assets", tags=["Assets"])
app.include_router(tle.router, prefix="/api/tle", tags=["TLE"])
app.include_router(screening.router, prefix="/api/screening", tags=["Screening"])
app.include_router(conjunctions.router, prefix="/api/conjunctions", tags=["Conjunctions"])
app.include_router(maneuvers.router, prefix="/api/maneuvers", tags=["Maneuvers"])
app.include_router(environment.router, prefix="/api/environment", tags=["Environment"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(orbit.router, prefix="/api/orbit", tags=["Orbit"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "SentinelSpace"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
