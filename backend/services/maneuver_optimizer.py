"""Collision avoidance maneuver planning.

Computes optimal avoidance maneuvers for a protected asset when facing
a high or critical conjunction event. Generates multiple maneuver options
with different directions, timings, and delta-v magnitudes.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from sgp4.api import Satrec, WGS72

from core.propagator import OrbitalPropagator
from core.tle_parser import TLEData
from utils.constants import MU_EARTH, R_EARTH
from utils.time_utils import datetime_to_jd

from .collision_probability import compute_collision_probability, classify_threat_level
from .uncertainty_model import (
    default_covariance_ric,
    covariance_ric_to_eci,
    estimate_hard_body_radius,
)

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

    Generates multiple options varying direction and timing:
    - In-track: most fuel-efficient (changes orbit phase)
    - Radial: changes altitude
    - Cross-track: changes orbital plane (least efficient)

    For each direction, tries multiple timings:
    - 0.5 orbits before TCA
    - 1.0 orbits before TCA
    - 2.0 orbits before TCA

    Args:
        asset_tle: TLE of the protected satellite.
        secondary_tle: TLE of the threat object.
        tca: Time of closest approach.
        current_miss_m: Current miss distance (meters).
        current_pc: Current collision probability.
        asset_radius_m: Asset hard-body radius.
        delta_v_budget_ms: Available delta-v budget (m/s). None = unlimited.
        pc_threshold: Target Pc to achieve.

    Returns:
        List of ManeuverOption sorted by delta_v (ascending).
    """
    options: list[ManeuverOption] = []

    try:
        primary_prop = OrbitalPropagator(asset_tle)
        # Get orbital period
        elements = primary_prop.get_orbital_elements(tca)
        period_sec = elements.period * 60.0  # minutes to seconds
    except Exception as e:
        logger.error("Failed to compute maneuver options: %s", e)
        return []

    directions = ["in_track", "radial", "cross_track"]
    timing_orbits = [0.5, 1.0, 2.0]
    label_idx = 0
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    for direction in directions:
        for t_orbits in timing_orbits:
            burn_dt = tca - timedelta(seconds=t_orbits * period_sec)
            if burn_dt < datetime.utcnow():
                continue  # Can't burn in the past

            # Compute required delta-v
            dv_ms = _compute_delta_v(
                primary_prop,
                asset_tle,
                secondary_tle,
                burn_dt,
                tca,
                direction,
                asset_radius_m,
                pc_threshold,
            )

            if dv_ms is None or dv_ms <= 0:
                continue

            if delta_v_budget_ms is not None and dv_ms > delta_v_budget_ms:
                continue

            # Compute post-maneuver state
            new_miss_m, new_pc = _evaluate_maneuver(
                primary_prop,
                asset_tle,
                secondary_tle,
                burn_dt,
                tca,
                direction,
                dv_ms,
                asset_radius_m,
            )

            # Fuel cost as percentage of budget
            fuel_pct = (dv_ms / delta_v_budget_ms * 100.0) if delta_v_budget_ms else 0.0

            label = labels[label_idx % len(labels)]
            label_idx += 1

            options.append(ManeuverOption(
                label=label,
                direction=direction,
                delta_v_ms=round(dv_ms, 4),
                timing_before_tca_orbits=t_orbits,
                burn_time=burn_dt,
                new_miss_distance_m=round(new_miss_m, 1),
                new_collision_probability=new_pc,
                fuel_cost_pct=round(fuel_pct, 2),
                original_miss_m=current_miss_m,
                original_pc=current_pc,
            ))

    options.sort(key=lambda o: o.delta_v_ms)
    return options


def _compute_delta_v(
    primary_prop: OrbitalPropagator,
    asset_tle: TLEData,
    secondary_tle: TLEData,
    burn_dt: datetime,
    tca: datetime,
    direction: str,
    asset_radius_m: float,
    target_pc: float,
) -> Optional[float]:
    """Compute minimum delta-v to reduce Pc below threshold.

    Uses bisection search on delta-v magnitude.
    """
    # Start with a range of delta-v values
    dv_low = 0.001  # 1 mm/s
    dv_high = 1.0   # 1 m/s

    # Check if high end is sufficient
    _, pc_high = _evaluate_maneuver(
        primary_prop, asset_tle, secondary_tle,
        burn_dt, tca, direction, dv_high, asset_radius_m,
    )

    if pc_high > target_pc:
        # Need more delta-v, try higher
        dv_high = 5.0
        _, pc_high = _evaluate_maneuver(
            primary_prop, asset_tle, secondary_tle,
            burn_dt, tca, direction, dv_high, asset_radius_m,
        )
        if pc_high > target_pc:
            return dv_high  # Return max even if not sufficient

    # Bisection to find minimum delta-v
    for _ in range(20):
        dv_mid = (dv_low + dv_high) / 2.0
        _, pc_mid = _evaluate_maneuver(
            primary_prop, asset_tle, secondary_tle,
            burn_dt, tca, direction, dv_mid, asset_radius_m,
        )

        if pc_mid > target_pc:
            dv_low = dv_mid
        else:
            dv_high = dv_mid

        if (dv_high - dv_low) < 0.0001:
            break

    return dv_high


def _evaluate_maneuver(
    primary_prop: OrbitalPropagator,
    asset_tle: TLEData,
    secondary_tle: TLEData,
    burn_dt: datetime,
    tca: datetime,
    direction: str,
    delta_v_ms: float,
    asset_radius_m: float,
) -> tuple[float, float]:
    """Evaluate a maneuver: compute post-maneuver miss distance and Pc.

    Applies a delta-v in the specified direction at burn_dt, then
    propagates to TCA to find the new conjunction geometry.

    Returns (new_miss_distance_m, new_collision_probability).
    """
    try:
        secondary_prop = OrbitalPropagator(secondary_tle)

        # Get primary state at burn time
        p1_burn = primary_prop.propagate(burn_dt)
        r1 = p1_burn.position_eci  # km
        v1 = p1_burn.velocity_eci  # km/s

        # Compute direction vector in ECI
        dv_vec = _direction_vector(r1, v1, direction) * (delta_v_ms / 1000.0)  # m/s -> km/s

        # Apply delta-v
        v1_new = v1 + dv_vec

        # Simple linear propagation to TCA (approximation)
        dt_seconds = (tca - burn_dt).total_seconds()
        # Use two-body approximation for post-maneuver position
        r1_tca = _two_body_propagate(r1, v1_new, dt_seconds)

        # Get secondary state at TCA
        p2_tca = secondary_prop.propagate(tca)

        # For more accurate results, we'd create a new TLE from the state vectors
        # but this approximation is reasonable for maneuver planning
        r2_tca = p2_tca.position_eci
        v2_tca = p2_tca.velocity_eci

        # Also need primary velocity at TCA (approximate)
        v1_tca = _two_body_velocity(r1, v1_new, dt_seconds)

        miss_m = np.linalg.norm(r1_tca - r2_tca) * 1000.0  # km -> m

        # Compute covariance
        primary_age = max(0.0, (tca - asset_tle.epoch).total_seconds() / 3600.0) if asset_tle.epoch else 48.0
        secondary_age = max(0.0, (tca - secondary_tle.epoch).total_seconds() / 3600.0) if secondary_tle.epoch else 72.0

        cov1 = covariance_ric_to_eci(default_covariance_ric(primary_age, "payload"), r1_tca, v1_tca)
        cov2 = covariance_ric_to_eci(default_covariance_ric(secondary_age, "unknown"), r2_tca, v2_tca)

        sec_radius = estimate_hard_body_radius(object_type="unknown")

        result = compute_collision_probability(
            r1_tca, v1_tca, r2_tca, v2_tca,
            cov1, cov2, asset_radius_m, sec_radius,
        )

        return (result.miss_distance_m, result.collision_probability)

    except Exception as e:
        logger.debug("Maneuver evaluation error: %s", e)
        return (0.0, 1.0)


def _direction_vector(r: np.ndarray, v: np.ndarray, direction: str) -> np.ndarray:
    """Compute unit direction vector in ECI for the given maneuver direction."""
    if direction == "in_track":
        v_mag = np.linalg.norm(v)
        return v / v_mag if v_mag > 1e-10 else np.array([1.0, 0.0, 0.0])

    elif direction == "radial":
        r_mag = np.linalg.norm(r)
        return r / r_mag if r_mag > 1e-10 else np.array([0.0, 0.0, 1.0])

    elif direction == "cross_track":
        h = np.cross(r, v)
        h_mag = np.linalg.norm(h)
        return h / h_mag if h_mag > 1e-10 else np.array([0.0, 1.0, 0.0])

    return np.array([1.0, 0.0, 0.0])


def _two_body_propagate(r0: np.ndarray, v0: np.ndarray, dt: float) -> np.ndarray:
    """Simple two-body propagation using universal variable method.

    For small dt relative to orbital period, a linear approximation
    with gravitational correction is used.
    """
    r0_mag = np.linalg.norm(r0)
    if r0_mag < 1e-10 or abs(dt) < 1e-10:
        return r0

    # For short propagation times, use series expansion
    mu = MU_EARTH
    r0_mag3 = r0_mag ** 3

    # Position at t (second-order approximation)
    accel = -mu * r0 / r0_mag3
    r_new = r0 + v0 * dt + 0.5 * accel * dt ** 2

    return r_new


def _two_body_velocity(r0: np.ndarray, v0: np.ndarray, dt: float) -> np.ndarray:
    """Approximate velocity after two-body propagation."""
    r0_mag = np.linalg.norm(r0)
    if r0_mag < 1e-10:
        return v0

    mu = MU_EARTH
    r0_mag3 = r0_mag ** 3

    accel = -mu * r0 / r0_mag3
    v_new = v0 + accel * dt

    return v_new
