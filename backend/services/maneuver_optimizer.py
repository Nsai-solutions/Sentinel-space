"""Collision avoidance maneuver planning.

Computes avoidance maneuver options using first-order orbital mechanics
approximations.  For each RIC direction (in-track, radial, cross-track)
and both +/- signs, estimates the position offset at TCA produced by a
given delta-v and recomputes miss distance and collision probability.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from core.propagator import OrbitalPropagator
from core.tle_parser import TLEData
from utils.constants import MU_EARTH

logger = logging.getLogger(__name__)


@dataclass
class ManeuverOption:
    """A computed avoidance maneuver option."""
    label: str
    direction: str  # "in_track", "radial", "cross_track"
    delta_v_ms: float  # m/s
    timing_before_tca_orbits: float
    burn_time: datetime
    new_miss_distance_m: float
    new_collision_probability: float
    fuel_cost_pct: float
    original_miss_m: float
    original_pc: float


def compute_avoidance_maneuvers(
    asset_tle: TLEData,
    secondary_tle: TLEData,
    tca: datetime,
    current_miss_m: float,
    current_pc: float,
    asset_radius_m: float = 1.0,
    delta_v_budget_ms: Optional[float] = None,
    pc_threshold: float = 1e-5,
) -> list[ManeuverOption]:
    """Compute avoidance maneuver options for a conjunction.

    Uses first-order approximations:
      - In-track ΔV  → along-track offset ≈ ΔV × time_to_TCA
      - Radial ΔV    → radial offset     ≈ ΔV × period / (2π)
      - Cross-track ΔV → cross-track offset ≈ ΔV × period / (2π)

    Generates options for each direction (±) and several ΔV magnitudes.
    """
    options: list[ManeuverOption] = []

    try:
        primary_prop = OrbitalPropagator(asset_tle)
        secondary_prop = OrbitalPropagator(secondary_tle)

        # Get orbital elements for period
        elements = primary_prop.get_orbital_elements(tca)
        period_sec = elements.period * 60.0  # minutes → seconds

        # Propagate both objects to TCA to get current geometry
        p1 = primary_prop.propagate(tca)
        p2 = secondary_prop.propagate(tca)

        r1 = np.asarray(p1.position_eci, dtype=float)  # km
        v1 = np.asarray(p1.velocity_eci, dtype=float)   # km/s
        r2 = np.asarray(p2.position_eci, dtype=float)
    except Exception as e:
        logger.error("Failed to set up maneuver computation: %s", e)
        return []

    # Decompose current miss into RIC components (meters)
    delta_r_m = (r2 - r1) * 1000.0  # km → m
    r1_m = r1 * 1000.0
    v1_ms = v1 * 1000.0

    r_mag = np.linalg.norm(r1_m)
    if r_mag < 1.0:
        logger.error("Primary position too small for RIC decomposition")
        return []

    e_r = r1_m / r_mag
    h = np.cross(r1_m, v1_ms)
    h_mag = np.linalg.norm(h)
    if h_mag < 1.0:
        logger.error("Angular momentum too small for RIC decomposition")
        return []

    e_c = h / h_mag
    e_i = np.cross(e_c, e_r)

    miss_radial = float(np.dot(delta_r_m, e_r))
    miss_in_track = float(np.dot(delta_r_m, e_i))
    miss_cross_track = float(np.dot(delta_r_m, e_c))

    # Time to TCA for the burn (assume 1 orbit before TCA as reference)
    time_to_tca_sec = period_sec  # default: 1 orbit

    # Hard body radius for Pc calculation
    combined_hbr = asset_radius_m + 1.0  # secondary default ~1m

    # ΔV magnitudes to try
    dv_magnitudes = [0.5, 1.0, 2.0, 5.0]

    directions = [
        ("in_track+",  "in_track",  +1),
        ("in_track-",  "in_track",  -1),
        ("radial+",    "radial",    +1),
        ("radial-",    "radial",    -1),
        ("cross_track+", "cross_track", +1),
        ("cross_track-", "cross_track", -1),
    ]

    label_idx = 0
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    for dv_ms in dv_magnitudes:
        if delta_v_budget_ms is not None and dv_ms > delta_v_budget_ms:
            continue

        for dir_label, direction, sign in directions:
            # First-order position offset at TCA (meters)
            if direction == "in_track":
                # In-track ΔV shifts along-track position: offset ≈ ΔV × Δt
                offset_in_track = sign * dv_ms * time_to_tca_sec
                offset_radial = 0.0
                offset_cross = 0.0
            elif direction == "radial":
                # Radial ΔV shifts radial position: offset ≈ ΔV × P/(2π)
                offset_radial = sign * dv_ms * period_sec / (2.0 * math.pi)
                offset_in_track = 0.0
                offset_cross = 0.0
            else:  # cross_track
                # Cross-track ΔV shifts cross-track: offset ≈ ΔV × P/(2π)
                offset_cross = sign * dv_ms * period_sec / (2.0 * math.pi)
                offset_radial = 0.0
                offset_in_track = 0.0

            # New miss distance components
            new_radial = miss_radial + offset_radial
            new_in_track = miss_in_track + offset_in_track
            new_cross = miss_cross_track + offset_cross

            new_miss_m = math.sqrt(new_radial**2 + new_in_track**2 + new_cross**2)

            # Recompute collision probability using simplified Foster formula
            new_pc = _foster_pc_simple(new_miss_m, combined_hbr)

            burn_dt = tca - timedelta(seconds=time_to_tca_sec)
            fuel_pct = (dv_ms / delta_v_budget_ms * 100.0) if delta_v_budget_ms else 0.0

            lbl = labels[label_idx % len(labels)]
            label_idx += 1

            options.append(ManeuverOption(
                label=lbl,
                direction=f"{direction} {'+'if sign > 0 else '-'}",
                delta_v_ms=round(dv_ms, 4),
                timing_before_tca_orbits=1.0,
                burn_time=burn_dt,
                new_miss_distance_m=round(new_miss_m, 1),
                new_collision_probability=new_pc,
                fuel_cost_pct=round(fuel_pct, 2),
                original_miss_m=current_miss_m,
                original_pc=current_pc,
            ))

    # Sort by (new Pc ascending, then ΔV ascending)
    options.sort(key=lambda o: (o.new_collision_probability, o.delta_v_ms))
    return options


def _foster_pc_simple(miss_m: float, combined_hbr_m: float) -> float:
    """Simplified 2D Gaussian collision probability estimate.

    Uses the Foster formula assuming circular, equal sigmas derived from
    the miss distance itself (sigma ≈ miss / 2 as a conservative estimate,
    with a floor of 50 m to avoid numerical issues).

    Pc ≈ (R² / (2 σ²)) × exp(-d² / (2 σ²))

    where d = miss distance, R = combined hard body radius, σ = position uncertainty.
    """
    if miss_m <= 0:
        return 1.0

    # Use a reasonable position uncertainty — scale with miss distance
    # Typical LEO covariance sigmas are 50-500 m; use max(miss/3, 50)
    sigma = max(miss_m / 3.0, 50.0)
    sigma_sq = sigma * sigma

    R = combined_hbr_m
    d_sq = miss_m * miss_m

    exponent = -d_sq / (2.0 * sigma_sq)
    if exponent < -500:
        return 0.0

    pc = (R * R / (2.0 * sigma_sq)) * math.exp(exponent)
    return max(0.0, min(1.0, pc))
