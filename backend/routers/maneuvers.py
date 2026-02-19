"""Collision avoidance maneuver API routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.tle_parser import parse_tle_text
from database.database import get_db
from database.models import Asset, ConjunctionEvent, ManeuverOption as ManeuverOptionDB
from models.schemas import ManeuverRequest, ManeuverOptionResponse
from services.maneuver_optimizer import compute_avoidance_maneuvers
from services.tle_catalog import catalog_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/compute", response_model=list[ManeuverOptionResponse])
def compute_maneuvers(req: ManeuverRequest, db: Session = Depends(get_db)):
    """Compute avoidance maneuver options for a conjunction."""
    event = db.query(ConjunctionEvent).filter(ConjunctionEvent.id == req.conjunction_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Conjunction event not found")

    asset = db.query(Asset).filter(Asset.id == event.primary_asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Get TLEs
    primary_tles = parse_tle_text(f"{asset.name}\n{asset.tle_line1}\n{asset.tle_line2}")
    secondary_tle = catalog_service.get_tle(event.secondary_norad_id)

    if not primary_tles or not secondary_tle:
        raise HTTPException(status_code=400, detail="Could not load required TLEs")

    try:
        options = compute_avoidance_maneuvers(
            asset_tle=primary_tles[0],
            secondary_tle=secondary_tle,
            tca=event.tca,
            current_miss_m=event.miss_distance_m,
            current_pc=event.collision_probability or 0.0,
            asset_radius_m=asset.hard_body_radius_m or 1.0,
            delta_v_budget_ms=asset.delta_v_budget_ms,
            pc_threshold=req.pc_threshold,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Maneuver computation failed: {e}")

    # Store options in database
    db_options = []
    for opt in options:
        db_opt = ManeuverOptionDB(
            conjunction_id=event.id,
            label=opt.label,
            direction=opt.direction,
            delta_v_ms=opt.delta_v_ms,
            timing_before_tca_orbits=opt.timing_before_tca_orbits,
            new_miss_distance_m=opt.new_miss_distance_m,
            new_collision_probability=opt.new_collision_probability,
            fuel_cost_pct=opt.fuel_cost_pct,
        )
        db.add(db_opt)
        db_options.append(db_opt)

    db.commit()

    for opt in db_options:
        db.refresh(opt)

    return [
        ManeuverOptionResponse(
            id=opt.id,
            label=opt.label,
            direction=opt.direction,
            delta_v_ms=opt.delta_v_ms,
            timing_before_tca_orbits=opt.timing_before_tca_orbits,
            new_miss_distance_m=opt.new_miss_distance_m,
            new_collision_probability=opt.new_collision_probability,
            fuel_cost_pct=opt.fuel_cost_pct,
            secondary_conjunctions_count=opt.secondary_conjunctions_count,
        )
        for opt in db_options
    ]


@router.post("/secondary-check")
def secondary_check(maneuver_id: int, db: Session = Depends(get_db)):
    """Check if a maneuver introduces secondary conjunctions."""
    # This would re-screen the modified orbit against the catalog
    # For now, return a placeholder
    return {
        "maneuver_id": maneuver_id,
        "secondary_conjunctions": [],
        "detail": "Secondary conjunction check placeholder",
    }


@router.get("/{maneuver_id}/report")
def maneuver_report(maneuver_id: int, db: Session = Depends(get_db)):
    """Generate a maneuver decision report."""
    opt = db.query(ManeuverOptionDB).filter(ManeuverOptionDB.id == maneuver_id).first()
    if not opt:
        raise HTTPException(status_code=404, detail="Maneuver option not found")

    event = db.query(ConjunctionEvent).filter(ConjunctionEvent.id == opt.conjunction_id).first()
    asset = db.query(Asset).filter(Asset.id == event.primary_asset_id).first() if event else None

    return {
        "maneuver": {
            "label": opt.label,
            "direction": opt.direction,
            "delta_v_ms": opt.delta_v_ms,
            "timing_orbits": opt.timing_before_tca_orbits,
            "new_miss_m": opt.new_miss_distance_m,
            "new_pc": opt.new_collision_probability,
            "fuel_cost_pct": opt.fuel_cost_pct,
        },
        "conjunction": {
            "tca": event.tca.isoformat() if event else None,
            "miss_distance_m": event.miss_distance_m if event else None,
            "collision_probability": event.collision_probability if event else None,
            "threat_level": event.threat_level.value if event and event.threat_level else None,
        },
        "asset": {
            "name": asset.name if asset else None,
            "norad_id": asset.norad_id if asset else None,
        },
        "recommendation": _generate_recommendation(opt, event),
    }


def _generate_recommendation(opt, event) -> str:
    """Generate a plain-text maneuver recommendation."""
    if not event:
        return "Insufficient data for recommendation."

    pc = event.collision_probability or 0.0
    new_pc = opt.new_collision_probability or 0.0

    if pc > 1e-3:
        urgency = "URGENT: Maneuver is strongly recommended."
    elif pc > 1e-4:
        urgency = "Maneuver recommended; continue monitoring if not executed."
    else:
        urgency = "Maneuver optional; continued monitoring is acceptable."

    reduction = ""
    if new_pc < pc:
        factor = pc / max(new_pc, 1e-20)
        reduction = f" This maneuver reduces collision probability by a factor of {factor:.0f}."

    return f"{urgency}{reduction} Delta-v: {opt.delta_v_ms:.4f} m/s ({opt.direction})."
