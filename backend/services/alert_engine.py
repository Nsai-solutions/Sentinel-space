"""Alert generation and management engine.

Monitors conjunction events for threat level changes and generates
alerts based on configurable thresholds.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Alert, AlertConfig, AlertStatus, ConjunctionEvent, ThreatLevel

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_CRITICAL = 1e-3
DEFAULT_HIGH = 1e-4
DEFAULT_MODERATE = 1e-5


def check_and_generate_alerts(
    db: Session,
    new_events: list[ConjunctionEvent],
    asset_id: int,
) -> list[Alert]:
    """Check new screening results and generate alerts as needed.

    Compares new events against alert configuration thresholds
    and generates appropriate alerts.
    """
    # Get alert config for this asset (or global)
    config = db.query(AlertConfig).filter(
        (AlertConfig.asset_id == asset_id) | (AlertConfig.asset_id.is_(None))
    ).first()

    critical_threshold = config.critical_threshold if config else DEFAULT_CRITICAL
    high_threshold = config.high_threshold if config else DEFAULT_HIGH

    alerts_generated: list[Alert] = []

    for event in new_events:
        if event.collision_probability is None:
            continue

        pc = event.collision_probability

        if pc > critical_threshold:
            alert = Alert(
                asset_id=asset_id,
                conjunction_id=event.id,
                threat_level=ThreatLevel.CRITICAL,
                message=f"CRITICAL: Conjunction with {event.secondary_name or event.secondary_norad_id} "
                        f"at TCA {event.tca.strftime('%Y-%m-%d %H:%M UTC')} - "
                        f"Pc={pc:.2e}, Miss={event.miss_distance_m:.0f}m",
                reason="new_critical",
                status=AlertStatus.NEW,
            )
            db.add(alert)
            alerts_generated.append(alert)

        elif pc > high_threshold:
            alert = Alert(
                asset_id=asset_id,
                conjunction_id=event.id,
                threat_level=ThreatLevel.HIGH,
                message=f"HIGH: Conjunction with {event.secondary_name or event.secondary_norad_id} "
                        f"at TCA {event.tca.strftime('%Y-%m-%d %H:%M UTC')} - "
                        f"Pc={pc:.2e}, Miss={event.miss_distance_m:.0f}m",
                reason="new_high",
                status=AlertStatus.NEW,
            )
            db.add(alert)
            alerts_generated.append(alert)

    if alerts_generated:
        db.commit()
        logger.info("Generated %d alerts for asset %d", len(alerts_generated), asset_id)
        _send_email_notifications(db, alerts_generated)

    return alerts_generated


def check_escalations(
    db: Session,
    old_events: dict[tuple[int, int], float],
    new_events: list[ConjunctionEvent],
    asset_id: int,
) -> list[Alert]:
    """Check if any existing conjunctions have escalated in threat level.

    Args:
        old_events: Dict mapping (primary_id, secondary_norad_id) to old Pc.
        new_events: New screening results.
        asset_id: ID of the protected asset.
    """
    alerts = []

    for event in new_events:
        if event.collision_probability is None:
            continue

        key = (event.primary_asset_id, event.secondary_norad_id)
        old_pc = old_events.get(key)

        if old_pc is not None:
            old_level = _classify(old_pc)
            new_level = _classify(event.collision_probability)

            if _threat_rank(new_level) > _threat_rank(old_level):
                alert = Alert(
                    asset_id=asset_id,
                    conjunction_id=event.id,
                    threat_level=ThreatLevel(new_level),
                    message=f"ESCALATION: {event.secondary_name or event.secondary_norad_id} "
                            f"threat increased from {old_level} to {new_level} "
                            f"(Pc: {old_pc:.2e} → {event.collision_probability:.2e})",
                    reason="escalation",
                    status=AlertStatus.NEW,
                )
                db.add(alert)
                alerts.append(alert)

    if alerts:
        db.commit()

    return alerts


def _classify(pc: float) -> str:
    if pc > DEFAULT_CRITICAL:
        return "CRITICAL"
    elif pc > DEFAULT_HIGH:
        return "HIGH"
    elif pc > DEFAULT_MODERATE:
        return "MODERATE"
    return "LOW"


def _threat_rank(level: str) -> int:
    return {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}.get(level, 0)


def _send_email_notifications(db: Session, alerts: list[Alert]):
    """Send email notifications for new alerts.  Never raises."""
    try:
        from database.models import NotificationPreferences, Asset
        from services.email_service import is_configured, send_alert_email, format_alert_email

        if not is_configured():
            return

        prefs = db.query(NotificationPreferences).first()
        if not prefs or not prefs.email_enabled or not prefs.email:
            return

        for alert in alerts:
            level = alert.threat_level.value if alert.threat_level else "LOW"

            should_send = (
                (level == "CRITICAL" and prefs.notify_critical) or
                (level == "HIGH" and prefs.notify_high) or
                (level == "MODERATE" and prefs.notify_moderate) or
                (level == "LOW" and prefs.notify_low)
            )
            if not should_send:
                continue

            asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
            asset_name = asset.name if asset else ""

            subject, html = format_alert_email(alert.message, level, asset_name)
            send_alert_email(prefs.email, subject, html)
    except Exception as e:
        logger.error("Email notification error (non-fatal): %s", e)
