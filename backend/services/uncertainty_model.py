"""Position uncertainty and covariance estimation.

When specific covariance data is unavailable (common for debris),
uses TLE-age-based uncertainty growth models to estimate position
uncertainty in the radial, in-track, and cross-track directions.
"""

from __future__ import annotations

import math

import numpy as np


def default_covariance_ric(
    tle_age_hours: float,
    object_type: str = "unknown",
) -> np.ndarray:
    """Estimate 3x3 covariance in RIC (radial, in-track, cross-track) frame.

    Uses TLE-age-based uncertainty growth model. Units: km^2.

    Args:
        tle_age_hours: Hours since TLE epoch.
        object_type: One of 'payload', 'debris', 'rocket_body', 'unknown'.

    Returns:
        3x3 diagonal covariance matrix in km^2.
    """
    age = max(0.0, tle_age_hours)

    # Base uncertainties (meters) at epoch
    if object_type == "payload":
        # Payloads generally have better tracking
        sigma_r = 30.0 + 3.0 * age
        sigma_i = 60.0 + 30.0 * age
        sigma_c = 30.0 + 3.0 * age
    elif object_type == "debris":
        sigma_r = 80.0 + 8.0 * age
        sigma_i = 150.0 + 80.0 * age
        sigma_c = 80.0 + 8.0 * age
    elif object_type == "rocket_body":
        sigma_r = 60.0 + 6.0 * age
        sigma_i = 120.0 + 60.0 * age
        sigma_c = 60.0 + 6.0 * age
    else:
        # Default / unknown
        sigma_r = 50.0 + 5.0 * age
        sigma_i = 100.0 + 50.0 * age
        sigma_c = 50.0 + 5.0 * age

    # Convert to km and square for covariance
    sigma_r_km = sigma_r / 1000.0
    sigma_i_km = sigma_i / 1000.0
    sigma_c_km = sigma_c / 1000.0

    return np.diag([sigma_r_km ** 2, sigma_i_km ** 2, sigma_c_km ** 2])


def covariance_ric_to_eci(
    cov_ric: np.ndarray,
    r_eci: np.ndarray,
    v_eci: np.ndarray,
) -> np.ndarray:
    """Transform covariance from RIC frame to ECI frame.

    Args:
        cov_ric: 3x3 covariance in RIC frame (km^2).
        r_eci: Position vector in ECI (km).
        v_eci: Velocity vector in ECI (km/s).

    Returns:
        3x3 covariance in ECI frame (km^2).
    """
    r_mag = np.linalg.norm(r_eci)
    if r_mag < 1e-10:
        return cov_ric

    # RIC basis vectors in ECI
    e_r = r_eci / r_mag
    h = np.cross(r_eci, v_eci)
    h_mag = np.linalg.norm(h)

    if h_mag < 1e-10:
        return cov_ric

    e_c = h / h_mag
    e_i = np.cross(e_c, e_r)

    # Rotation matrix from RIC to ECI
    R = np.column_stack([e_r, e_i, e_c])

    return R @ cov_ric @ R.T


def estimate_hard_body_radius(rcs: float | None = None, object_type: str = "unknown") -> float:
    """Estimate hard-body radius from radar cross-section (RCS).

    Args:
        rcs: Radar cross-section in m^2. If None, uses default by object type.
        object_type: Object type for default estimation.

    Returns:
        Estimated radius in meters.
    """
    if rcs is not None:
        if rcs < 0.01:
            return 0.05
        elif rcs < 0.1:
            return 0.15
        elif rcs < 1.0:
            return 0.5
        elif rcs < 10.0:
            return 1.5
        else:
            return 3.0

    # Default by object type
    defaults = {
        "payload": 2.0,
        "debris": 0.2,
        "rocket_body": 2.5,
        "unknown": 0.5,
    }
    return defaults.get(object_type, 0.5)


def gps_covariance() -> np.ndarray:
    """Covariance for satellites with GPS receivers (user's own satellites).

    Much smaller uncertainty: ~10m in each axis.

    Returns:
        3x3 covariance in km^2.
    """
    sigma_km = 0.01  # 10 meters in km
    return np.diag([sigma_km ** 2, sigma_km ** 2, sigma_km ** 2])
