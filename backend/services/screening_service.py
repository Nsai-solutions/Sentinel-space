"""Screening service — shared screening logic for API and background tasks.

Extracted from routers/screening.py so both the API endpoint and the
background auto-screening loop can call the same function without
circular imports.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from core.tle_parser import parse_tle_text
from database.models import (
    Asset, ConjunctionEvent, ConjunctionHistory, ScreeningJob,
    ThreatLevel, EventStatus, JobStatus,
)
from services.conjunction_screener import screen_asset
from services.alert_engine import check_and_generate_alerts
from services.tle_catalog import catalog_service
from services.uncertainty_model import default_covariance_ric, estimate_hard_body_radius

logger = logging.getLogger(__name__)


def run_screening_for_asset(
    db: Session,
    asset_id: int,
    time_window_days: float = 7.0,
    distance_threshold_km: float = 25.0,
    job_id: Optional[int] = None,
) -> Optional[int]:
    """Run conjunction screening for a single asset.

    If *job_id* is provided, updates that ScreeningJob's status.
    If *job_id* is ``None``, creates a new ScreeningJob automatically.

    Returns the job_id on success, or ``None`` on early failure.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        logger.warning("Asset %d not found for screening", asset_id)
        return None

    # Create job if not provided
    if job_id is None:
        job = ScreeningJob(
            asset_id=asset_id,
            status=JobStatus.PENDING,
            time_window_days=time_window_days,
            distance_threshold_km=distance_threshold_km,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id

    job = db.query(ScreeningJob).filter(ScreeningJob.id == job_id).first()
    if not job:
        return None

    job.status = JobStatus.RUNNING
    job.started_at = datetime.utcnow()
    db.commit()

    # --- Resolve asset TLE (prefer fresh catalog TLE) ---
    asset_tle = catalog_service.get_tle(asset.norad_id)
    if not asset_tle:
        tles = parse_tle_text(f"{asset.name}\n{asset.tle_line1}\n{asset.tle_line2}")
        asset_tle = tles[0] if tles else None
    if not asset_tle:
        job.status = JobStatus.FAILED
        job.error_message = "Failed to parse asset TLE"
        db.commit()
        return job_id

    # Ensure catalog is populated before screening
    catalog_service.ensure_catalog_populated(min_objects=500)
    catalog = catalog_service.get_all_tles()

    logger.info(
        "Screening asset=%s (NORAD %d), catalog_size=%d, window=%.1fd, threshold=%.1fkm",
        asset.name, asset.norad_id, len(catalog), time_window_days, distance_threshold_km,
    )

    if len(catalog) == 0:
        job.status = JobStatus.FAILED
        job.error_message = "TLE catalog is empty — refresh catalog first"
        db.commit()
        logger.error("Screening failed for asset %d: empty catalog", asset_id)
        return job_id

    # Clear old conjunction events for this asset before new screening
    old_events = db.query(ConjunctionEvent).filter(
        ConjunctionEvent.primary_asset_id == asset_id
    ).all()
    if old_events:
        logger.info("Clearing %d old conjunctions for asset %d", len(old_events), asset_id)
        for e in old_events:
            db.delete(e)
        db.commit()

    job.total_objects = len(catalog)
    db.commit()

    def progress_callback(pct, candidates, conjunctions):
        job.progress = float(pct)
        job.candidates_found = int(candidates)
        job.conjunctions_found = int(conjunctions)
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

    # Deduplicate: same secondary + same TCA (within 60 seconds) = duplicate
    seen: set = set()
    unique_results = []
    for r in results:
        key = (r.secondary_tle.catalog_number, round(r.tca.timestamp() / 60))
        if key not in seen:
            seen.add(key)
            unique_results.append(r)
        else:
            logger.debug("Skipping duplicate conjunction: %s at %s",
                         r.secondary_tle.name, r.tca)
    results = unique_results
    logger.info("Screening found %d unique conjunctions (removed %d duplicates)",
                len(results), len(screening_result.conjunctions) - len(results))

    # Store results in database
    new_events = []
    for r in results:
        # Compute uncertainty sigmas for storage
        pri_epoch = r.primary_tle.epoch_datetime
        if pri_epoch and hasattr(pri_epoch, 'tzinfo') and pri_epoch.tzinfo:
            pri_epoch = pri_epoch.replace(tzinfo=None)
        sec_epoch = r.secondary_tle.epoch_datetime
        if sec_epoch and hasattr(sec_epoch, 'tzinfo') and sec_epoch.tzinfo:
            sec_epoch = sec_epoch.replace(tzinfo=None)
        pri_age_h = max(0.0, (r.tca - pri_epoch).total_seconds() / 3600.0) if pri_epoch else 48.0
        sec_age_h = max(0.0, (r.tca - sec_epoch).total_seconds() / 3600.0) if sec_epoch else 72.0
        cov1 = default_covariance_ric(pri_age_h, "payload")
        cov2 = default_covariance_ric(sec_age_h, "unknown")
        sec_radius = estimate_hard_body_radius(object_type="unknown")

        event = ConjunctionEvent(
            primary_asset_id=asset_id,
            secondary_norad_id=int(r.secondary_tle.catalog_number),
            secondary_name=r.secondary_tle.name,
            tca=r.tca,
            miss_distance_m=float(r.miss_distance_m),
            radial_m=float(r.radial_m),
            in_track_m=float(r.in_track_m),
            cross_track_m=float(r.cross_track_m),
            relative_velocity_kms=float(r.relative_velocity_kms),
            collision_probability=float(r.collision_probability),
            threat_level=ThreatLevel(r.threat_level),
            screening_job_id=job_id,
            status=EventStatus.ACTIVE,
            primary_sigma_radial_m=float(math.sqrt(cov1[0, 0]) * 1000.0),
            primary_sigma_in_track_m=float(math.sqrt(cov1[1, 1]) * 1000.0),
            primary_sigma_cross_track_m=float(math.sqrt(cov1[2, 2]) * 1000.0),
            secondary_sigma_radial_m=float(math.sqrt(cov2[0, 0]) * 1000.0),
            secondary_sigma_in_track_m=float(math.sqrt(cov2[1, 1]) * 1000.0),
            secondary_sigma_cross_track_m=float(math.sqrt(cov2[2, 2]) * 1000.0),
            combined_hard_body_radius_m=float((asset.hard_body_radius_m or 1.0) + sec_radius),
        )
        db.add(event)
        new_events.append(event)

    db.commit()

    # Refresh to get IDs
    for e in new_events:
        db.refresh(e)

    # Record history snapshots for trend analysis
    for event in new_events:
        history = ConjunctionHistory(
            primary_asset_id=asset_id,
            secondary_norad_id=event.secondary_norad_id,
            secondary_name=event.secondary_name,
            tca=event.tca,
            miss_distance_m=event.miss_distance_m,
            radial_m=event.radial_m,
            in_track_m=event.in_track_m,
            cross_track_m=event.cross_track_m,
            relative_velocity_kms=event.relative_velocity_kms,
            collision_probability=event.collision_probability,
            threat_level=event.threat_level,
            screening_job_id=job_id,
        )
        db.add(history)
    db.commit()

    # Generate alerts
    check_and_generate_alerts(db, new_events, asset_id)

    # Finalize job
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

    logger.info("Screening complete for asset %d: %d conjunctions", asset_id, len(results))
    return job_id
