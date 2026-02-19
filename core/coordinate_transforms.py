"""Coordinate frame transformations for orbital mechanics.

Provides conversions between:
- ECI (Earth-Centered Inertial / TEME) <-> ECEF (Earth-Centered Earth-Fixed)
- ECEF <-> Geodetic (WGS84 lat/lon/alt)
- Geodetic -> 3D cartesian for rendering
- Look angles (azimuth/elevation) from ground observer to satellite

All angles in radians internally unless suffixed with _deg.
"""

from __future__ import annotations

import numpy as np

from utils.constants import (
    DEG_TO_RAD,
    ECCENTRICITY_SQ,
    R_EARTH_EQUATORIAL,
    RAD_TO_DEG,
)


# =============================================================================
# ECI <-> ECEF
# =============================================================================

def eci_to_ecef(position_eci: np.ndarray, gmst: float) -> np.ndarray:
    """Rotate ECI (TEME) to ECEF by Greenwich Mean Sidereal Time.

    Args:
        position_eci: [x, y, z] in km
        gmst: Greenwich Mean Sidereal Time in radians

    Returns:
        [x, y, z] in km (ECEF)
    """
    cos_g = np.cos(gmst)
    sin_g = np.sin(gmst)
    x, y, z = position_eci[0], position_eci[1], position_eci[2]
    return np.array([
        cos_g * x + sin_g * y,
        -sin_g * x + cos_g * y,
        z,
    ])


def ecef_to_eci(position_ecef: np.ndarray, gmst: float) -> np.ndarray:
    """Rotate ECEF to ECI (TEME) by Greenwich Mean Sidereal Time.

    Args:
        position_ecef: [x, y, z] in km
        gmst: GMST in radians

    Returns:
        [x, y, z] in km (ECI)
    """
    cos_g = np.cos(gmst)
    sin_g = np.sin(gmst)
    x, y, z = position_ecef[0], position_ecef[1], position_ecef[2]
    return np.array([
        cos_g * x - sin_g * y,
        sin_g * x + cos_g * y,
        z,
    ])


def eci_to_ecef_batch(
    positions_eci: np.ndarray, gmst_array: np.ndarray
) -> np.ndarray:
    """Vectorized ECI to ECEF conversion.

    Args:
        positions_eci: shape (N, 3) ECI positions in km
        gmst_array: shape (N,) GMST values in radians

    Returns:
        shape (N, 3) ECEF positions in km
    """
    cos_g = np.cos(gmst_array)
    sin_g = np.sin(gmst_array)

    result = np.empty_like(positions_eci)
    result[:, 0] = cos_g * positions_eci[:, 0] + sin_g * positions_eci[:, 1]
    result[:, 1] = -sin_g * positions_eci[:, 0] + cos_g * positions_eci[:, 1]
    result[:, 2] = positions_eci[:, 2]
    return result


# =============================================================================
# ECEF <-> Geodetic (WGS84)
# =============================================================================

def ecef_to_geodetic(
    position_ecef: np.ndarray,
) -> tuple[float, float, float]:
    """Convert ECEF to geodetic coordinates using Bowring iterative method.

    Args:
        position_ecef: [x, y, z] in km

    Returns:
        (latitude_deg, longitude_deg, altitude_km)
    """
    x, y, z = position_ecef[0], position_ecef[1], position_ecef[2]
    a = R_EARTH_EQUATORIAL
    e2 = ECCENTRICITY_SQ

    lon = np.arctan2(y, x)
    p = np.sqrt(x ** 2 + y ** 2)

    # Initial estimate
    lat = np.arctan2(z, p * (1.0 - e2))

    # Bowring iteration (converges in 2-3 iterations)
    for _ in range(5):
        sin_lat = np.sin(lat)
        n = a / np.sqrt(1.0 - e2 * sin_lat ** 2)
        lat_new = np.arctan2(z + e2 * n * sin_lat, p)
        if abs(lat_new - lat) < 1e-12:
            break
        lat = lat_new

    # Altitude
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    n = a / np.sqrt(1.0 - e2 * sin_lat ** 2)

    if abs(cos_lat) > 1e-10:
        alt = p / cos_lat - n
    else:
        alt = abs(z) / abs(sin_lat) - n * (1.0 - e2)

    return (lat * RAD_TO_DEG, lon * RAD_TO_DEG, alt)


def ecef_to_geodetic_batch(
    positions_ecef: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized ECEF to geodetic for N positions.

    Args:
        positions_ecef: shape (N, 3) ECEF positions in km

    Returns:
        (latitudes_deg, longitudes_deg, altitudes_km) each shape (N,)
    """
    x = positions_ecef[:, 0]
    y = positions_ecef[:, 1]
    z = positions_ecef[:, 2]
    a = R_EARTH_EQUATORIAL
    e2 = ECCENTRICITY_SQ

    lon = np.arctan2(y, x)
    p = np.sqrt(x ** 2 + y ** 2)
    lat = np.arctan2(z, p * (1.0 - e2))

    # Fixed iteration count for vectorization (no branching)
    for _ in range(5):
        sin_lat = np.sin(lat)
        n = a / np.sqrt(1.0 - e2 * sin_lat ** 2)
        lat = np.arctan2(z + e2 * n * sin_lat, p)

    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    n = a / np.sqrt(1.0 - e2 * sin_lat ** 2)

    alt = np.where(
        np.abs(cos_lat) > 1e-10,
        p / cos_lat - n,
        np.abs(z) / np.maximum(np.abs(sin_lat), 1e-20) - n * (1.0 - e2),
    )

    return (lat * RAD_TO_DEG, lon * RAD_TO_DEG, alt)


def geodetic_to_ecef(
    lat_deg: float, lon_deg: float, alt_km: float
) -> np.ndarray:
    """Convert geodetic to ECEF coordinates.

    Args:
        lat_deg: latitude in degrees
        lon_deg: longitude in degrees
        alt_km: altitude above WGS84 ellipsoid in km

    Returns:
        [x, y, z] in km
    """
    lat = lat_deg * DEG_TO_RAD
    lon = lon_deg * DEG_TO_RAD
    a = R_EARTH_EQUATORIAL
    e2 = ECCENTRICITY_SQ

    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    n = a / np.sqrt(1.0 - e2 * sin_lat ** 2)

    x = (n + alt_km) * cos_lat * np.cos(lon)
    y = (n + alt_km) * cos_lat * np.sin(lon)
    z = (n * (1.0 - e2) + alt_km) * sin_lat
    return np.array([x, y, z])


def geodetic_to_cartesian_render(
    lat_deg: float,
    lon_deg: float,
    alt_km: float,
    scale: float = 1.0,
) -> np.ndarray:
    """Convert geodetic to 3D cartesian for rendering on a unit sphere.

    Earth radius maps to `scale` units. Altitude is represented as
    a fraction above the sphere surface.

    Returns:
        [x, y, z] in rendering units
    """
    r = scale * (1.0 + alt_km / R_EARTH_EQUATORIAL)
    lat = lat_deg * DEG_TO_RAD
    lon = lon_deg * DEG_TO_RAD
    x = r * np.cos(lat) * np.cos(lon)
    y = r * np.cos(lat) * np.sin(lon)
    z = r * np.sin(lat)
    return np.array([x, y, z])


def eci_to_render_coords(
    position_eci: np.ndarray, scale: float = 1.0
) -> np.ndarray:
    """Convert ECI position (km) to rendering coordinates.

    Maps so that Earth radius = scale. Simply divides by R_EARTH_EQUATORIAL.
    """
    return position_eci / R_EARTH_EQUATORIAL * scale


def eci_to_render_coords_batch(
    positions_eci: np.ndarray, scale: float = 1.0
) -> np.ndarray:
    """Vectorized ECI to render coordinates.

    Args:
        positions_eci: shape (N, 3) in km

    Returns:
        shape (N, 3) in render units
    """
    return positions_eci / R_EARTH_EQUATORIAL * scale


# =============================================================================
# Look Angles (Observer -> Satellite)
# =============================================================================

def compute_look_angles(
    observer_lat_deg: float,
    observer_lon_deg: float,
    observer_alt_km: float,
    satellite_ecef: np.ndarray,
) -> tuple[float, float, float]:
    """Compute azimuth, elevation, and range from ground observer to satellite.

    Args:
        observer_lat_deg: observer latitude in degrees
        observer_lon_deg: observer longitude in degrees
        observer_alt_km: observer altitude in km
        satellite_ecef: satellite ECEF position in km

    Returns:
        (azimuth_deg, elevation_deg, range_km)
        azimuth: [0, 360) clockwise from North
        elevation: [-90, 90] above local horizon
    """
    obs_ecef = geodetic_to_ecef(observer_lat_deg, observer_lon_deg, observer_alt_km)
    delta = satellite_ecef - obs_ecef

    lat = observer_lat_deg * DEG_TO_RAD
    lon = observer_lon_deg * DEG_TO_RAD
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    sin_lon = np.sin(lon)
    cos_lon = np.cos(lon)

    dx, dy, dz = delta[0], delta[1], delta[2]

    # Transform to ENU (East-North-Up)
    east = -sin_lon * dx + cos_lon * dy
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    up = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz

    range_km = np.sqrt(east ** 2 + north ** 2 + up ** 2)
    elevation = np.arctan2(up, np.sqrt(east ** 2 + north ** 2)) * RAD_TO_DEG
    azimuth = np.arctan2(east, north) * RAD_TO_DEG

    if azimuth < 0:
        azimuth += 360.0

    return (azimuth, elevation, range_km)
