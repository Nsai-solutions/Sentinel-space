"""Alert management API routes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import Alert, AlertConfig, AlertStatus, NotificationPreferences, ThreatLevel
from models.schemas import AlertConfigRequest, AlertResponse, NotificationPrefsRequest

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


_NOTIF_DEFAULTS = {
    "email": None,
    "email_enabled": False,
    "notify_critical": True,
    "notify_high": True,
    "notify_moderate": False,
    "notify_low": False,
}


@router.get("/notifications")
def get_notification_prefs(db: Session = Depends(get_db)):
    """Get email notification preferences."""
    try:
        prefs = db.query(NotificationPreferences).first()
    except Exception as exc:
        logger.warning("Could not query notification_preferences: %s", exc)
        return _NOTIF_DEFAULTS

    if not prefs:
        return _NOTIF_DEFAULTS
    return {
        "email": prefs.email,
        "email_enabled": prefs.email_enabled,
        "notify_critical": prefs.notify_critical,
        "notify_high": prefs.notify_high,
        "notify_moderate": prefs.notify_moderate,
        "notify_low": prefs.notify_low,
    }


@router.put("/notifications")
def update_notification_prefs(req: NotificationPrefsRequest, db: Session = Depends(get_db)):
    """Update email notification preferences."""
    try:
        prefs = db.query(NotificationPreferences).first()
    except Exception as exc:
        logger.warning("notification_preferences table missing, creating: %s", exc)
        db.rollback()
        from database.database import _migrate_columns
        _migrate_columns()
        prefs = None

    if not prefs:
        prefs = NotificationPreferences()
        db.add(prefs)

    if req.email is not None:
        prefs.email = req.email
    if req.email_enabled is not None:
        prefs.email_enabled = req.email_enabled
    if req.notify_critical is not None:
        prefs.notify_critical = req.notify_critical
    if req.notify_high is not None:
        prefs.notify_high = req.notify_high
    if req.notify_moderate is not None:
        prefs.notify_moderate = req.notify_moderate
    if req.notify_low is not None:
        prefs.notify_low = req.notify_low

    db.commit()
    return {"detail": "Notification preferences saved"}


@router.post("/test-email")
def test_email(db: Session = Depends(get_db)):
    """Send a test email to verify Resend integration."""
    from services.email_service import is_configured, send_alert_email, format_alert_email

    if not is_configured():
        raise HTTPException(status_code=400, detail="Email not configured (RESEND_API_KEY not set)")

    try:
        prefs = db.query(NotificationPreferences).first()
    except Exception:
        prefs = None

    if not prefs or not prefs.email:
        raise HTTPException(status_code=400, detail="No recipient email configured in notification preferences")

    subject, html = format_alert_email(
        "This is a test alert from SentinelSpace. If you received this, email notifications are working.",
        "HIGH",
        "Test Asset",
    )
    ok = send_alert_email(prefs.email, subject, html)
    if ok:
        return {"detail": f"Test email sent to {prefs.email}"}
    raise HTTPException(status_code=500, detail="Failed to send test email — check server logs")
