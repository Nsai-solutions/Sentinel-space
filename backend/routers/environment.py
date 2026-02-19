"""Space environment API routes."""

from __future__ import annotations

import logging
import math

from fastapi import APIRouter

from services.tle_catalog import catalog_service
from utils.constants import R_EARTH

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/density")
def debris_density():
    """Get debris density data by altitude bin."""
    tles = catalog_service.get_all_tles()

    # Create altitude bins (every 50km from 100 to 2000km)
    bins = {}
    for alt_min in range(100, 2050, 50):
        bins[alt_min] = 0

    for tle in tles:
        try:
            # Compute approximate altitude from mean motion
            n = tle.mean_motion  # revs/day
            if n <= 0:
                continue
            n_rad = n * 2.0 * math.pi / 86400.0
            mu = 398600.4418
            a = (mu / (n_rad ** 2)) ** (1.0 / 3.0)
            alt = a - R_EARTH

            # Find matching bin
            bin_key = int(alt / 50) * 50
            if 100 <= bin_key < 2050:
                bins[bin_key] = bins.get(bin_key, 0) + 1
        except Exception:
            continue

    result = []
    for alt_min, count in sorted(bins.items()):
        # Shell volume: 4/3 * pi * ((R+h2)^3 - (R+h1)^3)
        r1 = R_EARTH + alt_min
        r2 = R_EARTH + alt_min + 50
        volume = (4.0 / 3.0) * math.pi * (r2 ** 3 - r1 ** 3)
        density = count / volume if volume > 0 else 0

        result.append({
            "altitude_min_km": alt_min,
            "altitude_max_km": alt_min + 50,
            "object_count": count,
            "density_per_km3": density,
        })

    return result


@router.get("/statistics")
def catalog_statistics():
    """Get catalog statistics and basic classification."""
    tles = catalog_service.get_all_tles()

    stats = {
        "total_objects": len(tles),
        "by_orbit_type": {"LEO": 0, "MEO": 0, "GEO": 0, "HEO": 0, "OTHER": 0},
        "last_refresh": None,
    }

    for tle in tles:
        try:
            n = tle.mean_motion
            if n <= 0:
                stats["by_orbit_type"]["OTHER"] += 1
                continue

            n_rad = n * 2.0 * math.pi / 86400.0
            mu = 398600.4418
            a = (mu / (n_rad ** 2)) ** (1.0 / 3.0)
            alt = a - R_EARTH

            if alt < 2000:
                stats["by_orbit_type"]["LEO"] += 1
            elif alt < 35000:
                stats["by_orbit_type"]["MEO"] += 1
            elif 35000 <= alt <= 36500:
                stats["by_orbit_type"]["GEO"] += 1
            else:
                stats["by_orbit_type"]["HEO"] += 1
        except Exception:
            stats["by_orbit_type"]["OTHER"] += 1

    catalog_stats = catalog_service.get_catalog_stats()
    stats["last_refresh"] = catalog_stats.get("last_refresh")

    return stats


@router.get("/hotspots")
def debris_hotspots():
    """Get known debris concentration zones."""
    return [
        {
            "name": "Cosmos-Iridium Collision Zone",
            "altitude_km": 790,
            "inclination_deg": 86.4,
            "description": "Debris from the 2009 Cosmos 2251/Iridium 33 collision",
            "estimated_objects": 2000,
        },
        {
            "name": "Fengyun-1C ASAT Test Zone",
            "altitude_km": 865,
            "inclination_deg": 98.8,
            "description": "Debris from the 2007 Chinese ASAT test",
            "estimated_objects": 3400,
        },
        {
            "name": "Soviet RORSAT Belt",
            "altitude_km": 1000,
            "inclination_deg": 65.0,
            "description": "Nuclear reactor coolant droplets from Soviet RORSAT missions",
            "estimated_objects": 16000,
        },
        {
            "name": "Sun-Synchronous Corridor",
            "altitude_km": 700,
            "inclination_deg": 98.0,
            "description": "High-traffic sun-synchronous orbit band used by Earth observation satellites",
            "estimated_objects": 5000,
        },
        {
            "name": "GEO Graveyard Belt",
            "altitude_km": 36050,
            "inclination_deg": 0.0,
            "description": "Graveyard orbit above GEO for decommissioned satellites",
            "estimated_objects": 400,
        },
    ]
