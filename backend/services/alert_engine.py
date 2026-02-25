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

    Uses the event's pre-computed threat_level (which accounts for both
    Pc thresholds AND miss-distance upgrades) instead of re-classifying
    from collision_probability alone.
    """
    logger.info(
        "check_and_generate_alerts called: asset_id=%d, events=%d",
        asset_id, len(new_events),
    )

    alerts_generated: list[Alert] = []

    for event in new_events:
        # Use the stored threat_level which already includes miss-distance
        # upgrades (e.g. miss < 200m → HIGH even if Pc is low)
        level_str = event.threat_level.value if event.threat_level else None
        if not level_str:
            continue

        pc = event.collision_probability
        miss = event.miss_distance_m

        if level_str in ("CRITICAL", "HIGH"):
            alert = Alert(
                asset_id=asset_id,
                conjunction_id=event.id,
                threat_level=ThreatLevel(level_str),
                message=(
                    f"{level_str}: Conjunction with "
                    f"{event.secondary_name or event.secondary_norad_id} "
                    f"at TCA {event.tca.strftime('%Y-%m-%d %H:%M UTC')} - "
                    f"Pc={pc:.2e}, Miss={miss:.0f}m"
                ),
                reason=f"new_{level_str.lower()}",
                status=AlertStatus.NEW,
            )
            db.add(alert)
            alerts_generated.append(alert)
            logger.info(
                "Alert created: %s for event %d (Pc=%.2e, miss=%.0fm)",
                level_str, event.id, pc or 0, miss or 0,
            )

    if alerts_generated:
        db.commit()
        logger.info("Generated %d alerts for asset %d", len(alerts_generated), asset_id)
        _send_email_notifications(db, alerts_generated)
    else:
        logger.info("No alerts generated for asset %d (no CRITICAL/HIGH events)", asset_id)

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
            logger.info("Email not configured (no RESEND_API_KEY) — skipping notifications")
            return

        prefs = db.query(NotificationPreferences).first()
        if not prefs:
            logger.info("No notification preferences found — skipping email")
            return
        if not prefs.email_enabled:
            logger.info("Email notifications disabled in preferences — skipping")
            return
        if not prefs.email:
            logger.info("No recipient email configured — skipping")
            return

        logger.info(
            "Email prefs: to=%s, critical=%s, high=%s, moderate=%s, low=%s",
            prefs.email, prefs.notify_critical, prefs.notify_high,
            prefs.notify_moderate, prefs.notify_low,
        )

        sent_count = 0
        for alert in alerts:
            level = alert.threat_level.value if alert.threat_level else "LOW"

            should_send = (
                (level == "CRITICAL" and prefs.notify_critical) or
                (level == "HIGH" and prefs.notify_high) or
                (level == "MODERATE" and prefs.notify_moderate) or
                (level == "LOW" and prefs.notify_low)
            )
            if not should_send:
                logger.info("Skipping email for alert %d (level=%s, not enabled)", alert.id, level)
                continue

            asset = db.query(Asset).filter(Asset.id == alert.asset_id).first()
            asset_name = asset.name if asset else ""

            subject, html = format_alert_email(alert.message, level, asset_name)
            logger.info("Sending alert email: to=%s, subject=%s", prefs.email, subject)
            ok = send_alert_email(prefs.email, subject, html)
            if ok:
                sent_count += 1

        logger.info("Email notifications complete: %d/%d sent", sent_count, len(alerts))
    except Exception as e:
        logger.error("Email notification error (non-fatal): %s", e)
