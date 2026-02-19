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

    # TLE-based uncertainty growth model.
    # In-track uncertainty dominates and grows rapidly with TLE age because
    # mean motion errors accumulate along-track. Typical SSN TLE accuracy:
    #   - Fresh TLE (0h): ~200m radial, ~500m in-track, ~200m cross-track
    #   - 24h old TLE:    ~500m radial, ~5km in-track, ~500m cross-track
    #   - 72h old TLE:    ~1km radial,  ~15km in-track, ~1km cross-track
    # These values produce operationally realistic Pc in the 1e-7 to 1e-3
    # range for conjunction events at typical screening thresholds (5-25km).
    if object_type == "payload":
        sigma_r = 200.0 + 12.0 * age
        sigma_i = 500.0 + 200.0 * age
        sigma_c = 200.0 + 12.0 * age
    elif object_type == "debris":
        sigma_r = 500.0 + 30.0 * age
        sigma_i = 1500.0 + 500.0 * age
        sigma_c = 500.0 + 30.0 * age
    elif object_type == "rocket_body":
        sigma_r = 400.0 + 25.0 * age
        sigma_i = 1000.0 + 400.0 * age
        sigma_c = 400.0 + 25.0 * age
    else:
        sigma_r = 300.0 + 20.0 * age
        sigma_i = 800.0 + 300.0 * age
        sigma_c = 300.0 + 20.0 * age

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

    # Default by object type (meters)
    defaults = {
        "payload": 3.0,
        "debris": 0.3,
        "rocket_body": 3.5,
        "unknown": 1.0,
    }
    return defaults.get(object_type, 1.0)


def gps_covariance() -> np.ndarray:
    """Covariance for satellites with GPS receivers (user's own satellites).

    Much smaller uncertainty: ~10m in each axis.

    Returns:
        3x3 covariance in km^2.
    """
    sigma_km = 0.01  # 10 meters in km
    return np.diag([sigma_km ** 2, sigma_km ** 2, sigma_km ** 2])
