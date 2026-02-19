"""Reporting and export API routes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Asset, ConjunctionEvent
from models.schemas import ReportRequest
from services.report_generator import generate_conjunction_report, generate_insurance_report

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/conjunction-summary")
def conjunction_summary_report(req: ReportRequest, db: Session = Depends(get_db)):
    """Generate conjunction summary PDF report."""
    # Get assets
    if req.asset_ids:
        assets = db.query(Asset).filter(Asset.id.in_(req.asset_ids)).all()
    else:
        assets = db.query(Asset).all()

    # Get conjunctions
    query = db.query(ConjunctionEvent)
    if req.asset_ids:
        query = query.filter(ConjunctionEvent.primary_asset_id.in_(req.asset_ids))
    if req.start_date:
        query = query.filter(ConjunctionEvent.tca >= req.start_date)
    if req.end_date:
        query = query.filter(ConjunctionEvent.tca <= req.end_date)

    events = query.order_by(ConjunctionEvent.collision_probability.desc()).all()

    assets_data = [
        {"name": a.name, "norad_id": a.norad_id, "orbit_type": a.orbit_type}
        for a in assets
    ]

    events_data = []
    for e in events:
        asset = db.query(Asset).filter(Asset.id == e.primary_asset_id).first()
        events_data.append({
            "primary_asset_name": asset.name if asset else "Unknown",
            "secondary_name": e.secondary_name,
            "secondary_norad_id": e.secondary_norad_id,
            "tca": e.tca.isoformat() if e.tca else "",
            "miss_distance_m": e.miss_distance_m,
            "collision_probability": e.collision_probability,
            "threat_level": e.threat_level.value if e.threat_level else "LOW",
        })

    pdf_bytes = generate_conjunction_report(
        assets=assets_data,
        conjunctions=events_data,
        start_date=req.start_date,
        end_date=req.end_date,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=conjunction_report.pdf"},
    )


@router.post("/insurance-risk")
def insurance_risk_report(req: ReportRequest, db: Session = Depends(get_db)):
    """Generate insurance risk assessment PDF."""
    if not req.asset_ids:
        raise HTTPException(status_code=400, detail="Specify at least one asset_id")

    asset = db.query(Asset).filter(Asset.id == req.asset_ids[0]).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    events = db.query(ConjunctionEvent).filter(
        ConjunctionEvent.primary_asset_id == asset.id,
    ).order_by(ConjunctionEvent.tca.asc()).all()

    asset_data = {
        "name": asset.name,
        "norad_id": asset.norad_id,
        "orbit_type": asset.orbit_type,
        "mass_kg": asset.mass_kg,
        "cross_section_m2": asset.cross_section_m2,
        "maneuverable": asset.maneuverable,
    }

    history_data = [
        {
            "tca": e.tca.isoformat() if e.tca else "",
            "miss_distance_m": e.miss_distance_m,
            "collision_probability": e.collision_probability,
            "threat_level": e.threat_level.value if e.threat_level else "LOW",
        }
        for e in events
    ]

    pdf_bytes = generate_insurance_report(asset_data, history_data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=insurance_risk_report.pdf"},
    )


@router.get("/export/conjunctions")
def export_conjunctions(
    format: str = "csv",
    asset_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Export conjunction data in CSV or JSON format."""
    query = db.query(ConjunctionEvent)
    if asset_id:
        query = query.filter(ConjunctionEvent.primary_asset_id == asset_id)

    events = query.order_by(ConjunctionEvent.tca.asc()).all()

    if format == "csv":
        lines = ["event_id,primary_asset_id,secondary_norad_id,secondary_name,tca,miss_distance_m,radial_m,in_track_m,cross_track_m,relative_velocity_kms,collision_probability,threat_level,status"]
        for e in events:
            lines.append(
                f"{e.id},{e.primary_asset_id},{e.secondary_norad_id},"
                f"\"{e.secondary_name or ''}\","
                f"{e.tca.isoformat() if e.tca else ''},"
                f"{e.miss_distance_m},{e.radial_m or ''},{e.in_track_m or ''},"
                f"{e.cross_track_m or ''},{e.relative_velocity_kms or ''},"
                f"{e.collision_probability or ''},{e.threat_level.value if e.threat_level else ''},"
                f"{e.status.value if e.status else ''}"
            )
        content = "\n".join(lines)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=conjunctions.csv"},
        )

    # JSON format
    data = []
    for e in events:
        data.append({
            "event_id": e.id,
            "primary_asset_id": e.primary_asset_id,
            "secondary_norad_id": e.secondary_norad_id,
            "secondary_name": e.secondary_name,
            "tca": e.tca.isoformat() if e.tca else None,
            "miss_distance_m": e.miss_distance_m,
            "collision_probability": e.collision_probability,
            "threat_level": e.threat_level.value if e.threat_level else None,
        })

    return data
