"""Conjunction screening API routes."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.tle_parser import parse_tle_text
from database.database import get_db
from database.models import (
    Asset, ConjunctionEvent, ScreeningJob, ThreatLevel, EventStatus, JobStatus,
)
from models.schemas import ScreeningRequest, ScreeningStatusResponse
from services.conjunction_screener import screen_asset
from services.alert_engine import check_and_generate_alerts
from services.tle_catalog import catalog_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Track running jobs
_running_jobs: dict[int, threading.Thread] = {}


@router.post("/run")
def run_screening(req: ScreeningRequest, db: Session = Depends(get_db)):
    """Trigger conjunction screening for one or more assets."""
    if not req.asset_ids:
        # Screen all assets
        assets = db.query(Asset).all()
        asset_ids = [a.id for a in assets]
    else:
        asset_ids = req.asset_ids

    if not asset_ids:
        raise HTTPException(status_code=400, detail="No assets to screen")

    jobs = []
    for asset_id in asset_ids:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            continue

        # Create screening job
        job = ScreeningJob(
            asset_id=asset_id,
            status=JobStatus.PENDING,
            time_window_days=req.time_window_days,
            distance_threshold_km=req.distance_threshold_km,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Launch screening in background thread
        t = threading.Thread(
            target=_run_screening_job,
            args=(job.id, asset_id, req.time_window_days, req.distance_threshold_km),
            daemon=True,
        )
        t.start()
        _running_jobs[job.id] = t

        jobs.append({"job_id": job.id, "asset_id": asset_id, "status": "RUNNING"})

    return {"jobs": jobs, "total": len(jobs)}


@router.get("/status/{job_id}", response_model=ScreeningStatusResponse)
def screening_status(job_id: int, db: Session = Depends(get_db)):
    """Check screening job progress."""
    job = db.query(ScreeningJob).filter(ScreeningJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return ScreeningStatusResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        total_objects=job.total_objects,
        candidates_found=job.candidates_found,
        conjunctions_found=job.conjunctions_found,
        error_message=job.error_message,
    )


@router.get("/results/{job_id}")
def screening_results(job_id: int, db: Session = Depends(get_db)):
    """Get screening results (conjunction events from a job)."""
    events = db.query(ConjunctionEvent).filter(
        ConjunctionEvent.screening_job_id == job_id
    ).order_by(ConjunctionEvent.collision_probability.desc()).all()

    return [_event_to_dict(e, db) for e in events]


def _run_screening_job(
    job_id: int,
    asset_id: int,
    time_window_days: float,
    distance_threshold_km: float,
):
    """Run screening in a background thread."""
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(ScreeningJob).filter(ScreeningJob.id == job_id).first()
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not job or not asset:
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        # Get asset TLE — prefer fresh catalog TLE over stale DB TLE
        asset_tle = catalog_service.get_tle(asset.norad_id)
        if not asset_tle:
            tles = parse_tle_text(f"{asset.name}\n{asset.tle_line1}\n{asset.tle_line2}")
            asset_tle = tles[0] if tles else None
        if not asset_tle:
            job.status = JobStatus.FAILED
            job.error_message = "Failed to parse asset TLE"
            db.commit()
            return
        catalog = catalog_service.get_all_tles()

        logger.info(
            "Screening job %d: asset=%s (NORAD %d), catalog_size=%d",
            job_id, asset.name, asset.norad_id, len(catalog),
        )

        if len(catalog) == 0:
            job.status = JobStatus.FAILED
            job.error_message = "TLE catalog is empty — refresh catalog first"
            db.commit()
            logger.error("Screening job %d failed: empty catalog", job_id)
            return

        job.total_objects = len(catalog)
        db.commit()

        def progress_callback(pct, candidates, conjunctions):
            job.progress = pct
            job.candidates_found = candidates
            job.conjunctions_found = conjunctions
            db.commit()

        # Run screening
        screening_result = screen_asset(
            asset_tle=asset_tle,
            catalog=catalog,
            time_window_days=time_window_days,
            distance_threshold_km=distance_threshold_km,
            step_seconds=60.0,
            progress_callback=progress_callback,
            asset_radius_m=asset.hard_body_radius_m or 1.0,
        )
        results = screening_result.conjunctions

        # Store results in database
        new_events = []
        for r in results:
            event = ConjunctionEvent(
                primary_asset_id=asset_id,
                secondary_norad_id=r.secondary_tle.catalog_number,
                secondary_name=r.secondary_tle.name,
                tca=r.tca,
                miss_distance_m=r.miss_distance_m,
                radial_m=r.radial_m,
                in_track_m=r.in_track_m,
                cross_track_m=r.cross_track_m,
                relative_velocity_kms=r.relative_velocity_kms,
                collision_probability=r.collision_probability,
                threat_level=ThreatLevel(r.threat_level),
                screening_job_id=job_id,
                status=EventStatus.ACTIVE,
            )
            db.add(event)
            new_events.append(event)

        db.commit()

        # Refresh to get IDs
        for e in new_events:
            db.refresh(e)

        # Generate alerts
        check_and_generate_alerts(db, new_events, asset_id)

        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        job.conjunctions_found = len(results)
        job.completed_at = datetime.utcnow()

        # Store closest miss info for user feedback
        if len(results) == 0 and screening_result.closest_miss_km < float("inf"):
            job.error_message = (
                f"Closest approach: {screening_result.closest_miss_km:.1f} km "
                f"({screening_result.closest_miss_object}) — "
                f"all above {distance_threshold_km} km threshold"
            )
        db.commit()

        logger.info("Screening job %d complete: %d conjunctions", job_id, len(results))

    except Exception as e:
        logger.error("Screening job %d failed: %s", job_id, e)
        try:
            job = db.query(ScreeningJob).filter(ScreeningJob.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        _running_jobs.pop(job_id, None)


def _event_to_dict(event: ConjunctionEvent, db: Session) -> dict:
    """Convert conjunction event to dict for API response."""
    asset = db.query(Asset).filter(Asset.id == event.primary_asset_id).first()
    time_to_tca = None
    if event.tca:
        delta = (event.tca - datetime.utcnow()).total_seconds()
        time_to_tca = delta / 3600.0 if delta > 0 else 0.0

    return {
        "id": event.id,
        "primary_asset_name": asset.name if asset else "Unknown",
        "primary_norad_id": asset.norad_id if asset else 0,
        "secondary_name": event.secondary_name,
        "secondary_norad_id": event.secondary_norad_id,
        "secondary_object_type": event.secondary_object_type,
        "tca": event.tca.isoformat() if event.tca else None,
        "time_to_tca_hours": time_to_tca,
        "miss_distance_m": event.miss_distance_m,
        "radial_m": event.radial_m,
        "in_track_m": event.in_track_m,
        "cross_track_m": event.cross_track_m,
        "relative_velocity_kms": event.relative_velocity_kms,
        "collision_probability": event.collision_probability,
        "threat_level": event.threat_level.value if event.threat_level else "LOW",
        "status": event.status.value if event.status else "ACTIVE",
    }
