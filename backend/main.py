"""SentinelSpace — FastAPI Backend Entry Point."""

from __future__ import annotations

import logging
import os
import sys
import threading
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
from routers import assets, tle, screening, conjunctions, maneuvers, environment, alerts, reports, orbit, api_keys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


_refresh_shutdown = threading.Event()


def _background_refresh_loop(interval_hours: float):
    """Background thread that periodically refreshes the TLE catalog and auto-screens assets."""
    from services.tle_catalog import catalog_service

    interval_seconds = interval_hours * 3600
    logger.info("Background TLE refresh thread started (interval: %.1fh)", interval_hours)

    while not _refresh_shutdown.is_set():
        if _refresh_shutdown.wait(timeout=interval_seconds):
            break

        logger.info("Background TLE refresh starting...")
        try:
            count = catalog_service.refresh_catalog()
            logger.info(
                "Background TLE refresh complete: %d new/updated, %d total",
                count,
                catalog_service.catalog_size,
            )
        except Exception as e:
            logger.error("Background TLE refresh failed: %s", e)
            continue  # Skip screening if refresh failed

        # Auto-screen all eligible assets after catalog refresh
        screening_enabled = os.environ.get("SCREENING_ENABLED", "true").lower() == "true"
        if not screening_enabled:
            logger.info("Auto-screening disabled via SCREENING_ENABLED env var")
            continue

        try:
            _auto_screen_assets()
        except Exception as e:
            logger.error("Background auto-screening failed: %s", e)

    logger.info("Background TLE refresh thread stopped")


def _auto_screen_assets():
    """Screen all assets with auto_screen=True sequentially."""
    from database.database import SessionLocal
    from database.models import Asset
    from services.screening_service import run_screening_for_asset

    db = SessionLocal()
    try:
        assets = db.query(Asset).filter(
            Asset.auto_screen == True  # noqa: E712
        ).all()

        if not assets:
            logger.info("No assets with auto_screen enabled — skipping")
            return

        total_conjunctions = 0
        logger.info("Auto-screening %d assets...", len(assets))

        for asset in assets:
            if _refresh_shutdown.is_set():
                logger.info("Shutdown requested, aborting auto-screening")
                break

            window = asset.screening_window_days or 7.0
            threshold = asset.screening_threshold_km or 25.0
            logger.info(
                "Auto-screening asset: %s (NORAD %d), window=%.1fd, threshold=%.1fkm",
                asset.name, asset.norad_id, window, threshold,
            )

            try:
                run_screening_for_asset(
                    db=db,
                    asset_id=asset.id,
                    time_window_days=window,
                    distance_threshold_km=threshold,
                )
                # Count conjunctions from the latest job
                from database.models import ScreeningJob, JobStatus
                latest_job = db.query(ScreeningJob).filter(
                    ScreeningJob.asset_id == asset.id,
                    ScreeningJob.status == JobStatus.COMPLETED,
                ).order_by(ScreeningJob.completed_at.desc()).first()
                if latest_job:
                    total_conjunctions += latest_job.conjunctions_found or 0
            except Exception as e:
                logger.error("Auto-screening failed for asset %s (ID %d): %s",
                             asset.name, asset.id, e)

        logger.info(
            "Auto-screening complete: %d assets screened, %d total conjunctions found",
            len(assets), total_conjunctions,
        )
    finally:
        db.close()


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

    # Start background refresh thread (skip on Vercel serverless)
    _refresh_thread = None
    is_vercel = os.environ.get("VERCEL") or os.environ.get("IS_VERCEL")
    if not is_vercel:
        refresh_hours = float(os.environ.get("TLE_REFRESH_HOURS", "6"))
        _refresh_thread = threading.Thread(
            target=_background_refresh_loop,
            args=(refresh_hours,),
            daemon=True,
            name="tle-refresh",
        )
        _refresh_thread.start()
        logger.info("Background TLE refresh scheduled every %.1f hours", refresh_hours)
    else:
        logger.info("Vercel detected, skipping background TLE refresh")

    yield

    logger.info("SentinelSpace shutting down")
    _refresh_shutdown.set()
    if _refresh_thread is not None:
        _refresh_thread.join(timeout=5)


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

# Optional API key authentication (only active when API_KEY_REQUIRED=true)
from middleware.auth import APIKeyMiddleware
app.add_middleware(APIKeyMiddleware)

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
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["API Keys"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "SentinelSpace"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
