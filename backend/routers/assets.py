"""Asset management API routes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.propagator import OrbitalPropagator
from core.tle_parser import TLEData, parse_tle_text
from core.orbital_mechanics import classify_orbit
from database.database import get_db
from database.models import Asset, ConjunctionEvent, ThreatLevel
from models.schemas import AssetCreate, AssetDetail, AssetProperties, AssetResponse
from services.tle_catalog import catalog_service
from utils.time_utils import tle_epoch_to_datetime

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=AssetResponse)
def add_asset(req: AssetCreate, db: Session = Depends(get_db)):
    """Add a protected satellite by NORAD ID or TLE lines."""
    tle_data: Optional[TLEData] = None

    if req.tle_line1 and req.tle_line2:
        # Parse provided TLE
        name = req.name or "Custom Satellite"
        try:
            tles = parse_tle_text(f"{name}\n{req.tle_line1}\n{req.tle_line2}")
            if tles:
                tle_data = tles[0]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid TLE: {e}")

    elif req.norad_id:
        # Fetch from CelesTrak
        tle_data = catalog_service.fetch_by_norad_id(req.norad_id)
        if not tle_data:
            raise HTTPException(status_code=404, detail=f"Could not find TLE for NORAD ID {req.norad_id}")

    elif req.name:
        # Search by name
        results = catalog_service.search(req.name)
        if results:
            tle_data = results[0]
        else:
            raise HTTPException(status_code=404, detail=f"No satellite found for '{req.name}'")

    else:
        raise HTTPException(status_code=400, detail="Provide norad_id, name, or TLE lines")

    # Check for duplicates
    existing = db.query(Asset).filter(Asset.norad_id == tle_data.catalog_number).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Asset {tle_data.catalog_number} already exists")

    # Determine orbit type
    orbit_type = None
    try:
        prop = OrbitalPropagator(tle_data)
        elements = prop.get_orbital_elements(datetime.utcnow())
        orbit_type = elements.orbit_type
    except Exception:
        pass

    # Parse epoch
    epoch = None
    try:
        epoch = tle_data.epoch_datetime
    except Exception:
        pass

    # Add to catalog so it's available for screening
    catalog_service.add_tle(tle_data)

    asset = Asset(
        norad_id=tle_data.catalog_number,
        name=tle_data.name,
        tle_line1=tle_data.line1,
        tle_line2=tle_data.line2,
        tle_epoch=epoch,
        orbit_type=orbit_type,
        mass_kg=req.mass_kg,
        cross_section_m2=req.cross_section_m2,
        hard_body_radius_m=req.hard_body_radius_m,
        maneuverable=req.maneuverable,
        delta_v_budget_ms=req.delta_v_budget_ms,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return _asset_to_response(asset, db)


@router.get("", response_model=list[AssetResponse])
def list_assets(db: Session = Depends(get_db)):
    """List all protected assets."""
    assets = db.query(Asset).all()
    return [_asset_to_response(a, db) for a in assets]


@router.get("/{asset_id}", response_model=AssetDetail)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    """Get detailed asset information including current position."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    detail = _asset_to_detail(asset, db)
    return detail


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    """Remove a protected asset."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    db.delete(asset)
    db.commit()
    return {"detail": f"Asset {asset.norad_id} removed"}


@router.put("/{asset_id}/properties", response_model=AssetResponse)
def update_properties(asset_id: int, props: AssetProperties, db: Session = Depends(get_db)):
    """Update physical properties of an asset."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if props.mass_kg is not None:
        asset.mass_kg = props.mass_kg
    if props.cross_section_m2 is not None:
        asset.cross_section_m2 = props.cross_section_m2
    if props.hard_body_radius_m is not None:
        asset.hard_body_radius_m = props.hard_body_radius_m
    if props.maneuverable is not None:
        asset.maneuverable = props.maneuverable
    if props.delta_v_budget_ms is not None:
        asset.delta_v_budget_ms = props.delta_v_budget_ms

    db.commit()
    db.refresh(asset)
    return _asset_to_response(asset, db)


def _asset_to_response(asset: Asset, db: Session) -> AssetResponse:
    """Convert DB asset to response schema with threat summary."""
    # Count active conjunctions by threat level
    conj_counts = {}
    for level in ThreatLevel:
        count = db.query(ConjunctionEvent).filter(
            ConjunctionEvent.primary_asset_id == asset.id,
            ConjunctionEvent.threat_level == level,
        ).count()
        if count > 0:
            conj_counts[level.value] = count

    total_conj = sum(conj_counts.values())

    return AssetResponse(
        id=asset.id,
        norad_id=asset.norad_id,
        name=asset.name,
        orbit_type=asset.orbit_type,
        tle_epoch=asset.tle_epoch,
        mass_kg=asset.mass_kg,
        cross_section_m2=asset.cross_section_m2,
        maneuverable=asset.maneuverable,
        threat_summary=conj_counts,
        active_conjunctions=total_conj,
    )


def _asset_to_detail(asset: Asset, db: Session) -> AssetDetail:
    """Convert DB asset to detailed response with current position."""
    resp = _asset_to_response(asset, db)

    detail = AssetDetail(
        **resp.model_dump(),
        tle_line1=asset.tle_line1,
        tle_line2=asset.tle_line2,
        hard_body_radius_m=asset.hard_body_radius_m,
        delta_v_budget_ms=asset.delta_v_budget_ms,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )

    # Compute current position
    try:
        tle = _asset_to_tle(asset)
        prop = OrbitalPropagator(tle)
        now = datetime.utcnow()
        result = prop.propagate(now)
        elements = prop.get_orbital_elements(now)

        detail.latitude = result.latitude
        detail.longitude = result.longitude
        detail.altitude_km = result.altitude
        detail.velocity_kms = result.speed

        detail.orbital_elements = {
            "semi_major_axis_km": elements.semi_major_axis,
            "eccentricity": elements.eccentricity,
            "inclination_deg": elements.inclination,
            "raan_deg": elements.raan,
            "arg_perigee_deg": elements.arg_perigee,
            "true_anomaly_deg": elements.true_anomaly,
            "period_min": elements.period,
            "apogee_alt_km": elements.apogee_altitude,
            "perigee_alt_km": elements.perigee_altitude,
            "orbit_type": elements.orbit_type,
        }
    except Exception as e:
        logger.warning("Could not propagate asset %s: %s", asset.norad_id, e)

    return detail


def _asset_to_tle(asset: Asset) -> TLEData:
    """Convert a DB asset back to TLEData for propagation."""
    tles = parse_tle_text(f"{asset.name}\n{asset.tle_line1}\n{asset.tle_line2}")
    if not tles:
        raise ValueError(f"Could not parse TLE for asset {asset.norad_id}")
    return tles[0]
