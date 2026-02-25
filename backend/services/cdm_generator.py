"""Conjunction Data Message (CDM) generator.

Generates CDM messages following the CCSDS 508.0-B-1 standard format.
"""

from __future__ import annotations

import logging
from datetime import datetime

from database.models import Asset, ConjunctionEvent

logger = logging.getLogger(__name__)

# Field width for alignment (CCSDS uses fixed-width key = value format)
_KW = 34


def _kv(key: str, value: str) -> str:
    """Format a CDM key-value pair with consistent alignment."""
    return f"{key:<{_KW}}= {value}"


def generate_cdm(event: ConjunctionEvent, asset: Asset) -> str:
    """Generate a CDM text string for a conjunction event.

    Follows the CCSDS 508.0-B-1 Conjunction Data Message standard format.
    All required data is taken from the existing ConjunctionEvent and Asset
    model fields — no external lookups needed.
    """
    now = datetime.utcnow()
    tca = event.tca

    lines: list[str] = []

    # ── Header ──────────────────────────────────────────────
    lines.append(_kv("CCSDS_CDM_VERS", "1.0"))
    lines.append(_kv("CREATION_DATE", now.strftime("%Y-%m-%dT%H:%M:%S.000")))
    lines.append(_kv("ORIGINATOR", "SENTINELSPACE"))
    lines.append(_kv("MESSAGE_FOR", asset.name))
    lines.append(_kv("MESSAGE_ID", f"SSP-{event.id:06d}-{now.strftime('%Y%m%d%H%M%S')}"))
    lines.append(_kv("TCA", tca.strftime("%Y-%m-%dT%H:%M:%S.000") if tca else "N/A"))
    lines.append(_kv("MISS_DISTANCE", f"{event.miss_distance_m:.3f} [m]"))

    if event.relative_velocity_kms is not None:
        lines.append(_kv("RELATIVE_SPEED", f"{event.relative_velocity_kms * 1000:.3f} [m/s]"))

    if event.radial_m is not None:
        lines.append(_kv("RELATIVE_POSITION_R", f"{event.radial_m:.3f} [m]"))
    if event.in_track_m is not None:
        lines.append(_kv("RELATIVE_POSITION_T", f"{event.in_track_m:.3f} [m]"))
    if event.cross_track_m is not None:
        lines.append(_kv("RELATIVE_POSITION_N", f"{event.cross_track_m:.3f} [m]"))

    if event.collision_probability is not None:
        lines.append(_kv("COLLISION_PROBABILITY", f"{event.collision_probability:.10e}"))
    lines.append(_kv("COLLISION_PROBABILITY_METHOD", "FOSTER-1992"))

    lines.append("")

    # ── Object 1 (Primary / Protected) ─────────────────────
    lines.append(_kv("OBJECT", "OBJECT1"))
    lines.append(_kv("OBJECT_DESIGNATOR", str(asset.norad_id)))
    lines.append(_kv("CATALOG_NAME", "SATCAT"))
    lines.append(_kv("OBJECT_NAME", asset.name))
    lines.append(_kv("EPHEMERIS_NAME", "SGP4/SDP4"))
    lines.append(_kv("COVARIANCE_METHOD", "CALCULATED"))
    lines.append(_kv("MANEUVERABLE", "YES" if asset.maneuverable else "N/A"))

    # Covariance diagonal (variance = sigma^2, convert m→km for CCSDS)
    if event.primary_sigma_radial_m is not None:
        cr_r = (event.primary_sigma_radial_m / 1000.0) ** 2
        lines.append(_kv("CR_R", f"{cr_r:.10e}"))
    lines.append(_kv("CT_R", "0.0"))
    if event.primary_sigma_in_track_m is not None:
        ct_t = (event.primary_sigma_in_track_m / 1000.0) ** 2
        lines.append(_kv("CT_T", f"{ct_t:.10e}"))
    lines.append(_kv("CN_R", "0.0"))
    lines.append(_kv("CN_T", "0.0"))
    if event.primary_sigma_cross_track_m is not None:
        cn_n = (event.primary_sigma_cross_track_m / 1000.0) ** 2
        lines.append(_kv("CN_N", f"{cn_n:.10e}"))

    lines.append("")

    # ── Object 2 (Secondary / Threat) ──────────────────────
    lines.append(_kv("OBJECT", "OBJECT2"))
    lines.append(_kv("OBJECT_DESIGNATOR", str(event.secondary_norad_id)))
    lines.append(_kv("CATALOG_NAME", "SATCAT"))
    lines.append(_kv("OBJECT_NAME", event.secondary_name or "UNKNOWN"))
    lines.append(_kv("EPHEMERIS_NAME", "SGP4/SDP4"))
    lines.append(_kv("COVARIANCE_METHOD", "CALCULATED"))
    lines.append(_kv("MANEUVERABLE", "N/A"))

    if event.secondary_sigma_radial_m is not None:
        cr_r = (event.secondary_sigma_radial_m / 1000.0) ** 2
        lines.append(_kv("CR_R", f"{cr_r:.10e}"))
    lines.append(_kv("CT_R", "0.0"))
    if event.secondary_sigma_in_track_m is not None:
        ct_t = (event.secondary_sigma_in_track_m / 1000.0) ** 2
        lines.append(_kv("CT_T", f"{ct_t:.10e}"))
    lines.append(_kv("CN_R", "0.0"))
    lines.append(_kv("CN_T", "0.0"))
    if event.secondary_sigma_cross_track_m is not None:
        cn_n = (event.secondary_sigma_cross_track_m / 1000.0) ** 2
        lines.append(_kv("CN_N", f"{cn_n:.10e}"))

    # Combined hard-body radius
    if event.combined_hard_body_radius_m is not None:
        lines.append("")
        lines.append(f"COMMENT COMBINED_HBR = {event.combined_hard_body_radius_m:.3f} [m]")

    return "\n".join(lines)
