"""Orbital mechanics utilities.

Compute classical Keplerian elements from state vectors,
classify orbit types, and calculate derived orbital parameters.
"""

from __future__ import annotations

import math

import numpy as np

from utils.constants import (
    GEO_ALT,
    LEO_MAX_ALT,
    MU_EARTH,
    R_EARTH_EQUATORIAL,
    RAD_TO_DEG,
    SIDEREAL_DAY_SECONDS,
    TWO_PI,
)


def state_vectors_to_elements(
    r: np.ndarray, v: np.ndarray
) -> dict[str, float]:
    """Compute classical Keplerian elements from ECI state vectors.

    Args:
        r: position vector [x, y, z] in km (ECI)
        v: velocity vector [vx, vy, vz] in km/s (ECI)

    Returns:
        Dictionary with orbital elements and derived quantities.
    """
    mu = MU_EARTH
    r_mag = np.linalg.norm(r)
    v_mag = np.linalg.norm(v)

    # Specific angular momentum
    h = np.cross(r, v)
    h_mag = np.linalg.norm(h)

    # Node vector (k_hat x h)
    k_hat = np.array([0.0, 0.0, 1.0])
    n = np.cross(k_hat, h)
    n_mag = np.linalg.norm(n)

    # Eccentricity vector
    e_vec = ((v_mag ** 2 - mu / r_mag) * r - np.dot(r, v) * v) / mu
    ecc = np.linalg.norm(e_vec)

    # Specific energy
    energy = v_mag ** 2 / 2.0 - mu / r_mag

    # Semi-major axis
    if abs(1.0 - ecc) > 1e-10:
        sma = -mu / (2.0 * energy)
    else:
        sma = float("inf")

    # Inclination
    inc_rad = math.acos(np.clip(h[2] / h_mag, -1.0, 1.0))

    # RAAN (Right Ascension of Ascending Node)
    if n_mag > 1e-10:
        raan_rad = math.acos(np.clip(n[0] / n_mag, -1.0, 1.0))
        if n[1] < 0:
            raan_rad = TWO_PI - raan_rad
    else:
        raan_rad = 0.0

    # Argument of perigee
    if n_mag > 1e-10 and ecc > 1e-10:
        aop_rad = math.acos(
            np.clip(np.dot(n, e_vec) / (n_mag * ecc), -1.0, 1.0)
        )
        if e_vec[2] < 0:
            aop_rad = TWO_PI - aop_rad
    elif ecc > 1e-10:
        # Equatorial orbit: measure from x-axis
        aop_rad = math.acos(np.clip(e_vec[0] / ecc, -1.0, 1.0))
        if e_vec[1] < 0:
            aop_rad = TWO_PI - aop_rad
    else:
        aop_rad = 0.0

    # True anomaly
    if ecc > 1e-10:
        ta_rad = math.acos(
            np.clip(np.dot(e_vec, r) / (ecc * r_mag), -1.0, 1.0)
        )
        if np.dot(r, v) < 0:
            ta_rad = TWO_PI - ta_rad
    elif n_mag > 1e-10:
        # Circular non-equatorial: measure from ascending node
        ta_rad = math.acos(
            np.clip(np.dot(n, r) / (n_mag * r_mag), -1.0, 1.0)
        )
        if r[2] < 0:
            ta_rad = TWO_PI - ta_rad
    else:
        # Circular equatorial: measure from x-axis
        ta_rad = math.acos(np.clip(r[0] / r_mag, -1.0, 1.0))
        if r[1] < 0:
            ta_rad = TWO_PI - ta_rad

    # Derived quantities
    if sma != float("inf") and sma > 0:
        period = TWO_PI * math.sqrt(sma ** 3 / mu)
        apogee_alt = sma * (1.0 + ecc) - R_EARTH_EQUATORIAL
        perigee_alt = sma * (1.0 - ecc) - R_EARTH_EQUATORIAL
    else:
        period = float("inf")
        apogee_alt = float("inf")
        perigee_alt = sma * (1.0 - ecc) - R_EARTH_EQUATORIAL if sma != float("inf") else 0.0

    inc_deg = inc_rad * RAD_TO_DEG
    orbit_type = classify_orbit(sma, ecc, inc_deg, period)

    return {
        "semi_major_axis": sma,
        "eccentricity": ecc,
        "inclination": inc_deg,
        "raan": raan_rad * RAD_TO_DEG,
        "arg_perigee": aop_rad * RAD_TO_DEG,
        "true_anomaly": ta_rad * RAD_TO_DEG,
        "period": period,
        "apogee_alt": apogee_alt,
        "perigee_alt": perigee_alt,
        "orbit_type": orbit_type,
        "specific_energy": energy,
        "angular_momentum": h_mag,
        "velocity": v_mag,
    }


def classify_orbit(
    semi_major_axis: float,
    eccentricity: float,
    inclination_deg: float,
    period_seconds: float,
) -> str:
    """Classify orbit type based on orbital parameters.

    Returns one of: LEO, MEO, GEO, GSO, HEO, SSO, Molniya, OTHER
    """
    if semi_major_axis == float("inf") or semi_major_axis <= 0:
        return "OTHER"

    alt = semi_major_axis - R_EARTH_EQUATORIAL

    # GEO / GSO check
    if abs(period_seconds - SIDEREAL_DAY_SECONDS) < 1800 and eccentricity < 0.01:
        if inclination_deg < 1.0:
            return "GEO"
        return "GSO"

    # Molniya
    if (
        62.0 <= inclination_deg <= 64.0
        and eccentricity > 0.6
        and 43000 <= period_seconds <= 43800
    ):
        return "Molniya"

    # HEO (Highly Elliptical)
    apogee_alt = semi_major_axis * (1.0 + eccentricity) - R_EARTH_EQUATORIAL
    if eccentricity > 0.25 and apogee_alt > GEO_ALT:
        return "HEO"

    # SSO (Sun-Synchronous)
    if 96.0 <= inclination_deg <= 102.0 and 200 < alt < 1000:
        return "SSO"

    # MEO
    if LEO_MAX_ALT <= alt <= GEO_ALT:
        return "MEO"

    # LEO
    if alt < LEO_MAX_ALT:
        return "LEO"

    return "OTHER"


def compute_orbital_period(semi_major_axis: float) -> float:
    """Orbital period in seconds: T = 2*pi * sqrt(a^3 / mu)."""
    if semi_major_axis <= 0:
        return float("inf")
    return TWO_PI * math.sqrt(semi_major_axis ** 3 / MU_EARTH)


def compute_velocity_at_radius(
    semi_major_axis: float, radius: float
) -> float:
    """Vis-viva equation: v = sqrt(mu * (2/r - 1/a))."""
    if semi_major_axis <= 0 or radius <= 0:
        return 0.0
    val = MU_EARTH * (2.0 / radius - 1.0 / semi_major_axis)
    return math.sqrt(max(0.0, val))


def compute_specific_energy(semi_major_axis: float) -> float:
    """Specific orbital energy: epsilon = -mu / (2*a)."""
    if semi_major_axis <= 0:
        return 0.0
    return -MU_EARTH / (2.0 * semi_major_axis)


def compute_angular_momentum(r: np.ndarray, v: np.ndarray) -> float:
    """Specific angular momentum magnitude: |r x v|."""
    return float(np.linalg.norm(np.cross(r, v)))
