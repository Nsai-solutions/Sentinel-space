"""SentinelSpace — FastAPI Backend Entry Point."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
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

    yield

    logger.info("SentinelSpace shutting down")


app = FastAPI(
    title="SentinelSpace",
    description="Space Debris Threat Assessment Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
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
