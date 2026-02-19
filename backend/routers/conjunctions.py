"""Conjunction event API routes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.tle_parser import parse_tle_text
from database.database import get_db
from database.models import Asset, ConjunctionEvent, EventStatus, ThreatLevel
from models.schemas import ConjunctionDetail, ConjunctionResponse
from services.collision_probability import run_monte_carlo
from services.uncertainty_model import default_covariance_ric, covariance_ric_to_eci, estimate_hard_body_radius
from core.propagator import OrbitalPropagator
from services.tle_catalog import catalog_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=list[ConjunctionResponse])
def list_conjunctions(
    threat_level: Optional[str] = None,
    asset_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List active conjunction events with filtering."""
    query = db.query(ConjunctionEvent)

    if threat_level:
        query = query.filter(ConjunctionEvent.threat_level == ThreatLevel(threat_level))
    if asset_id:
        query = query.filter(ConjunctionEvent.primary_asset_id == asset_id)
    if status:
        query = query.filter(ConjunctionEvent.status == EventStatus(status))

    query = query.order_by(
        ConjunctionEvent.threat_level.desc(),
        ConjunctionEvent.tca.asc(),
    )

    events = query.offset(offset).limit(limit).all()

    results = []
    for event in events:
        asset = db.query(Asset).filter(Asset.id == event.primary_asset_id).first()
        time_to_tca = None
        if event.tca:
            delta = (event.tca - datetime.utcnow()).total_seconds()
            time_to_tca = delta / 3600.0 if delta > 0 else 0.0

        results.append(ConjunctionResponse(
            id=event.id,
            primary_asset_name=asset.name if asset else "Unknown",
            primary_norad_id=asset.norad_id if asset else 0,
            secondary_name=event.secondary_name,
            secondary_norad_id=event.secondary_norad_id,
            secondary_object_type=event.secondary_object_type,
            tca=event.tca,
            time_to_tca_hours=time_to_tca,
            miss_distance_m=event.miss_distance_m,
            relative_velocity_kms=event.relative_velocity_kms,
            collision_probability=event.collision_probability,
            threat_level=event.threat_level,
            status=event.status,
        ))

    return results


@router.get("/summary")
def conjunction_summary(db: Session = Depends(get_db)):
    """Get threat level summary counts."""
    counts = {}
    for level in ThreatLevel:
        count = db.query(ConjunctionEvent).filter(
            ConjunctionEvent.threat_level == level,
            ConjunctionEvent.status == EventStatus.ACTIVE,
        ).count()
        counts[level.value] = count

    return {
        "total": sum(counts.values()),
        "by_level": counts,
    }


@router.get("/{event_id}")
def get_conjunction_detail(event_id: int, db: Session = Depends(get_db)):
    """Get detailed conjunction analysis."""
    event = db.query(ConjunctionEvent).filter(ConjunctionEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Conjunction event not found")

    asset = db.query(Asset).filter(Asset.id == event.primary_asset_id).first()

    time_to_tca = None
    if event.tca:
        delta = (event.tca - datetime.utcnow()).total_seconds()
        time_to_tca = delta / 3600.0 if delta > 0 else 0.0

    # Get secondary object info from catalog
    secondary_tle = catalog_service.get_tle(event.secondary_norad_id)

    result = {
        "id": event.id,
        "primary": {
            "name": asset.name if asset else "Unknown",
            "norad_id": asset.norad_id if asset else 0,
            "mass_kg": asset.mass_kg if asset else None,
            "cross_section_m2": asset.cross_section_m2 if asset else None,
            "maneuverable": asset.maneuverable if asset else False,
        },
        "secondary": {
            "name": event.secondary_name or (secondary_tle.name if secondary_tle else "Unknown"),
            "norad_id": event.secondary_norad_id,
            "object_type": event.secondary_object_type,
        },
        "tca": event.tca.isoformat() if event.tca else None,
        "time_to_tca_hours": time_to_tca,
        "miss_distance_m": event.miss_distance_m,
        "radial_m": event.radial_m,
        "in_track_m": event.in_track_m,
        "cross_track_m": event.cross_track_m,
        "relative_velocity_kms": event.relative_velocity_kms,
        "collision_probability": event.collision_probability,
        "max_collision_probability": event.max_collision_probability,
        "threat_level": event.threat_level.value if event.threat_level else "LOW",
        "combined_hard_body_radius_m": event.combined_hard_body_radius_m,
        "uncertainty": {
            "primary_sigma_radial_m": event.primary_sigma_radial_m,
            "primary_sigma_in_track_m": event.primary_sigma_in_track_m,
            "primary_sigma_cross_track_m": event.primary_sigma_cross_track_m,
            "secondary_sigma_radial_m": event.secondary_sigma_radial_m,
            "secondary_sigma_in_track_m": event.secondary_sigma_in_track_m,
            "secondary_sigma_cross_track_m": event.secondary_sigma_cross_track_m,
        },
        "status": event.status.value if event.status else "ACTIVE",
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }

    # Add maneuver options if any
    options = []
    for opt in event.maneuver_options:
        options.append({
            "id": opt.id,
            "label": opt.label,
            "direction": opt.direction,
            "delta_v_ms": opt.delta_v_ms,
            "timing_before_tca_orbits": opt.timing_before_tca_orbits,
            "new_miss_distance_m": opt.new_miss_distance_m,
            "new_collision_probability": opt.new_collision_probability,
            "fuel_cost_pct": opt.fuel_cost_pct,
        })
    result["maneuver_options"] = options

    return result


@router.get("/{event_id}/history")
def conjunction_history(event_id: int, db: Session = Depends(get_db)):
    """Get screening history for a conjunction pair."""
    event = db.query(ConjunctionEvent).filter(ConjunctionEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Find all events with same primary/secondary pair
    history = db.query(ConjunctionEvent).filter(
        ConjunctionEvent.primary_asset_id == event.primary_asset_id,
        ConjunctionEvent.secondary_norad_id == event.secondary_norad_id,
    ).order_by(ConjunctionEvent.created_at.asc()).all()

    return [
        {
            "id": h.id,
            "tca": h.tca.isoformat() if h.tca else None,
            "miss_distance_m": h.miss_distance_m,
            "collision_probability": h.collision_probability,
            "threat_level": h.threat_level.value if h.threat_level else "LOW",
            "screened_at": h.created_at.isoformat() if h.created_at else None,
        }
        for h in history
    ]


@router.post("/{event_id}/monte-carlo")
def monte_carlo_analysis(event_id: int, n_samples: int = 10000, db: Session = Depends(get_db)):
    """Run Monte Carlo collision probability analysis."""
    event = db.query(ConjunctionEvent).filter(ConjunctionEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    asset = db.query(Asset).filter(Asset.id == event.primary_asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    try:
        # Get TLEs
        primary_tles = parse_tle_text(f"{asset.name}\n{asset.tle_line1}\n{asset.tle_line2}")
        secondary_tle = catalog_service.get_tle(event.secondary_norad_id)

        if not primary_tles or not secondary_tle:
            raise HTTPException(status_code=400, detail="Could not load TLEs")

        primary_tle = primary_tles[0]
        primary_prop = OrbitalPropagator(primary_tle)
        secondary_prop = OrbitalPropagator(secondary_tle)

        # Propagate to TCA
        p1 = primary_prop.propagate(event.tca)
        p2 = secondary_prop.propagate(event.tca)

        # Get covariances
        import numpy as np
        primary_age = max(0.0, (event.tca - primary_tle.epoch).total_seconds() / 3600.0) if primary_tle.epoch else 48.0
        secondary_age = max(0.0, (event.tca - secondary_tle.epoch).total_seconds() / 3600.0) if secondary_tle.epoch else 72.0

        cov1 = covariance_ric_to_eci(
            default_covariance_ric(primary_age, "payload"),
            p1.position_eci, p1.velocity_eci,
        )
        cov2 = covariance_ric_to_eci(
            default_covariance_ric(secondary_age, "unknown"),
            p2.position_eci, p2.velocity_eci,
        )

        r1_m = asset.hard_body_radius_m or 1.0
        r2_m = estimate_hard_body_radius(object_type="unknown")

        result = run_monte_carlo(
            p1.position_eci, p1.velocity_eci,
            p2.position_eci, p2.velocity_eci,
            cov1, cov2, r1_m, r2_m,
            n_samples=n_samples,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Monte Carlo analysis failed: {e}")


@router.post("/{event_id}/acknowledge")
def acknowledge_conjunction(event_id: int, db: Session = Depends(get_db)):
    """Mark a conjunction event as acknowledged."""
    event = db.query(ConjunctionEvent).filter(ConjunctionEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.status = EventStatus.ACKNOWLEDGED
    db.commit()
    return {"detail": "Event acknowledged"}
