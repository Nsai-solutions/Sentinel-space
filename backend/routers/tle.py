"""TLE data API routes."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from core.tle_parser import parse_tle_text
from models.schemas import TLEResponse, TLEUpload
from services.tle_catalog import catalog_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/fetch/{norad_id}", response_model=TLEResponse)
def fetch_tle(norad_id: int):
    """Fetch latest TLE from CelesTrak by NORAD ID."""
    tle = catalog_service.fetch_by_norad_id(norad_id)
    if not tle:
        raise HTTPException(status_code=404, detail=f"TLE not found for NORAD ID {norad_id}")

    return TLEResponse(
        norad_id=tle.catalog_number,
        name=tle.name,
        line1=tle.line1,
        line2=tle.line2,
        epoch=tle.epoch.isoformat() if tle.epoch else None,
        inclination=tle.inclination,
    )


@router.post("/upload", response_model=list[TLEResponse])
def upload_tle(data: TLEUpload):
    """Upload custom TLE data (text with one or more TLE sets)."""
    try:
        tles = parse_tle_text(data.tle_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse TLE: {e}")

    if not tles:
        raise HTTPException(status_code=400, detail="No valid TLEs found in uploaded text")

    catalog_service.add_tles(tles)

    return [
        TLEResponse(
            norad_id=tle.catalog_number,
            name=tle.name,
            line1=tle.line1,
            line2=tle.line2,
            epoch=tle.epoch.isoformat() if tle.epoch else None,
            inclination=tle.inclination,
        )
        for tle in tles
    ]


@router.get("/catalog/stats")
def catalog_stats():
    """Get catalog statistics."""
    return catalog_service.get_catalog_stats()


@router.get("/search")
def search_tle(q: str):
    """Search the TLE catalog by name or NORAD ID."""
    results = catalog_service.search(q)
    return [
        TLEResponse(
            norad_id=tle.catalog_number,
            name=tle.name,
            line1=tle.line1,
            line2=tle.line2,
            epoch=tle.epoch.isoformat() if tle.epoch else None,
            inclination=tle.inclination,
        )
        for tle in results[:100]
    ]


@router.post("/refresh")
def refresh_catalog():
    """Trigger a full catalog refresh from CelesTrak."""
    count = catalog_service.refresh_catalog()
    return {"detail": f"Refreshed catalog: {count} TLEs loaded", "total": catalog_service.catalog_size}
