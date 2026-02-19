"""Orbit propagation API routes."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from core.propagator import OrbitalPropagator
from core.tle_parser import parse_tle_text
from models.schemas import OrbitalElementsResponse, PropagationPoint
from services.tle_catalog import catalog_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_tle(norad_id: int):
    """Look up TLE from catalog, then database, then CelesTrak."""
    tle = catalog_service.get_tle(norad_id)
    if tle:
        return tle

    # Fallback: check user-added assets in database
    from database.database import SessionLocal
    from database.models import Asset

    db = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.norad_id == norad_id).first()
        if asset and asset.tle_line1 and asset.tle_line2:
            parsed = parse_tle_text(f"{asset.name}\n{asset.tle_line1}\n{asset.tle_line2}")
            if parsed:
                tle = parsed[0]
                catalog_service.add_tle(tle)
                return tle
    finally:
        db.close()

    # Last resort: try fetching from CelesTrak
    return catalog_service.fetch_by_norad_id(norad_id)


@router.get("/{norad_id}/propagate")
def propagate_satellite(
    norad_id: int,
    minutes: float = Query(default=0, description="Minutes from now to propagate"),
    steps: int = Query(default=1, le=1000, description="Number of time steps"),
    step_seconds: float = Query(default=60.0, description="Seconds between steps"),
):
    """Propagate a satellite and return position data."""
    tle = _resolve_tle(norad_id)
    if not tle:
        raise HTTPException(status_code=404, detail=f"TLE not found for NORAD {norad_id}")

    try:
        prop = OrbitalPropagator(tle)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Propagation error: {e}")

    start_dt = datetime.utcnow() + timedelta(minutes=minutes)
    results = []

    if steps == 1:
        try:
            r = prop.propagate(start_dt)
            results.append(PropagationPoint(
                datetime_utc=start_dt.isoformat(),
                latitude=r.latitude,
                longitude=r.longitude,
                altitude_km=r.altitude,
                velocity_kms=r.speed,
                in_shadow=r.in_shadow,
                position_eci=r.position_eci.tolist(),
                velocity_eci=r.velocity_eci.tolist(),
            ))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Propagation failed: {e}")
    else:
        end_dt = start_dt + timedelta(seconds=step_seconds * (steps - 1))
        try:
            prop_results = prop.propagate_range(start_dt, end_dt, step_seconds=step_seconds)
            for r in prop_results:
                results.append(PropagationPoint(
                    datetime_utc=r.datetime_utc.isoformat(),
                    latitude=r.latitude,
                    longitude=r.longitude,
                    altitude_km=r.altitude,
                    velocity_kms=r.speed,
                    in_shadow=r.in_shadow,
                    position_eci=r.position_eci.tolist(),
                    velocity_eci=r.velocity_eci.tolist(),
                ))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Propagation failed: {e}")

    return {"norad_id": norad_id, "name": tle.name, "points": results}


@router.get("/{norad_id}/elements", response_model=OrbitalElementsResponse)
def orbital_elements(norad_id: int):
    """Get current orbital elements for a satellite."""
    tle = _resolve_tle(norad_id)
    if not tle:
        raise HTTPException(status_code=404, detail=f"TLE not found for NORAD {norad_id}")

    try:
        prop = OrbitalPropagator(tle)
        elements = prop.get_orbital_elements(datetime.utcnow())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not compute elements: {e}")

    return OrbitalElementsResponse(
        semi_major_axis_km=elements.semi_major_axis,
        eccentricity=elements.eccentricity,
        inclination_deg=elements.inclination,
        raan_deg=elements.raan,
        arg_perigee_deg=elements.arg_perigee,
        true_anomaly_deg=elements.true_anomaly,
        period_min=elements.period,
        apogee_alt_km=elements.apogee_altitude,
        perigee_alt_km=elements.perigee_altitude,
        orbit_type=elements.orbit_type,
        specific_energy=elements.specific_energy,
        angular_momentum=elements.angular_momentum,
    )


@router.get("/{norad_id}/ground-track")
def ground_track(
    norad_id: int,
    periods: float = Query(default=1.0, description="Number of orbital periods"),
    steps: int = Query(default=360, le=1000),
):
    """Get ground track points for a satellite."""
    tle = _resolve_tle(norad_id)
    if not tle:
        raise HTTPException(status_code=404, detail=f"TLE not found for NORAD {norad_id}")

    try:
        prop = OrbitalPropagator(tle)
        track = prop.get_ground_track(datetime.utcnow(), periods=periods, steps=steps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ground track computation failed: {e}")

    return {
        "norad_id": norad_id,
        "name": tle.name,
        "points": [
            {
                "datetime_utc": p.datetime_utc.isoformat(),
                "latitude": p.latitude,
                "longitude": p.longitude,
                "altitude_km": p.altitude,
                "in_shadow": p.in_shadow,
            }
            for p in track
        ],
    }


@router.post("/propagate-batch")
def propagate_batch(
    norad_ids: list[int],
    minutes: float = 0,
):
    """Propagate multiple satellites at a single time step."""
    dt = datetime.utcnow() + timedelta(minutes=minutes)
    results = []

    for nid in norad_ids:
        tle = _resolve_tle(nid)
        if not tle:
            continue

        try:
            prop = OrbitalPropagator(tle)
            r = prop.propagate(dt)
            results.append({
                "norad_id": nid,
                "name": tle.name,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "altitude_km": r.altitude,
                "velocity_kms": r.speed,
                "position_eci": r.position_eci.tolist(),
                "in_shadow": r.in_shadow,
            })
        except Exception:
            continue

    return {"datetime_utc": dt.isoformat(), "satellites": results}
