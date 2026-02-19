"""Alert management API routes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Alert, AlertConfig, AlertStatus, ThreatLevel
from models.schemas import AlertConfigRequest, AlertResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    status: Optional[str] = None,
    threat_level: Optional[str] = None,
    asset_id: Optional[int] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List alerts with optional filtering."""
    query = db.query(Alert)

    if status:
        query = query.filter(Alert.status == AlertStatus(status))
    if threat_level:
        query = query.filter(Alert.threat_level == ThreatLevel(threat_level))
    if asset_id:
        query = query.filter(Alert.asset_id == asset_id)

    query = query.order_by(Alert.created_at.desc())
    alerts = query.offset(offset).limit(limit).all()

    return [
        AlertResponse(
            id=a.id,
            asset_id=a.asset_id,
            conjunction_id=a.conjunction_id,
            threat_level=a.threat_level,
            message=a.message,
            reason=a.reason,
            status=a.status.value if a.status else "NEW",
            created_at=a.created_at,
            acknowledged_at=a.acknowledged_at,
        )
        for a in alerts
    ]


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db)):
    """Get count of unread (NEW) alerts."""
    count = db.query(Alert).filter(Alert.status == AlertStatus.NEW).count()
    return {"unread": count}


@router.put("/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    """Acknowledge an alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = datetime.utcnow()
    db.commit()
    return {"detail": "Alert acknowledged"}


@router.post("/configure")
def configure_alerts(config: AlertConfigRequest, db: Session = Depends(get_db)):
    """Set alert thresholds (global or per-asset)."""
    # Find existing config or create new
    query = db.query(AlertConfig)
    if config.asset_id:
        query = query.filter(AlertConfig.asset_id == config.asset_id)
    else:
        query = query.filter(AlertConfig.asset_id.is_(None))

    existing = query.first()

    if existing:
        existing.critical_threshold = config.critical_threshold
        existing.high_threshold = config.high_threshold
        existing.moderate_threshold = config.moderate_threshold
        existing.min_distance_km = config.min_distance_km
        existing.enabled = config.enabled
    else:
        new_config = AlertConfig(
            asset_id=config.asset_id,
            critical_threshold=config.critical_threshold,
            high_threshold=config.high_threshold,
            moderate_threshold=config.moderate_threshold,
            min_distance_km=config.min_distance_km,
            enabled=config.enabled,
        )
        db.add(new_config)

    db.commit()
    return {"detail": "Alert configuration saved"}
