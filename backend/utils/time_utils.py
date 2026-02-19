"""Time conversion utilities for orbital propagation.

Provides conversions between Python datetime, Julian Date, GMST,
and TLE epoch formats. Includes vectorized batch operations for
performance-critical propagation paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
from sgp4.api import jday

from utils.constants import (
    AU_KM,
    DEG_TO_RAD,
    SECONDS_PER_DAY,
    TWO_PI,
)


@dataclass(frozen=True, slots=True)
class JulianDate:
    """Split Julian Date for SGP4 compatibility.

    SGP4 expects jd (integer part) and fr (fractional part)
    as separate floats for numerical precision.
    """

    jd: float
    fr: float

    @property
    def full(self) -> float:
        return self.jd + self.fr


def datetime_to_jd(dt: datetime) -> JulianDate:
    """Convert Python datetime (UTC) to split Julian Date."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = dt.second + dt.microsecond / 1e6
    jd_val, fr_val = jday(
        dt.year, dt.month, dt.day, dt.hour, dt.minute, seconds
    )
    return JulianDate(jd=jd_val, fr=fr_val)


def jd_to_datetime(jd: JulianDate) -> datetime:
    """Convert split Julian Date back to Python datetime (UTC)."""
    total_jd = jd.full
    # Julian Date to calendar date algorithm
    z = int(total_jd + 0.5)
    f = (total_jd + 0.5) - z

    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - int(alpha / 4)

    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)

    day_frac = b - d - int(30.6001 * e) + f
    day = int(day_frac)
    frac = day_frac - day

    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715

    hours_frac = frac * 24.0
    hour = int(hours_frac)
    mins_frac = (hours_frac - hour) * 60.0
    minute = int(mins_frac)
    secs_frac = (mins_frac - minute) * 60.0
    second = int(secs_frac)
    microsecond = int((secs_frac - second) * 1e6)

    return datetime(
        year, month, day, hour, minute, second, microsecond,
        tzinfo=timezone.utc,
    )


def datetime_to_gmst(dt: datetime) -> float:
    """Compute Greenwich Mean Sidereal Time in radians.

    Uses the IAU 1982 GMST model for consistency with SGP4 TEME frame.
    """
    jd = datetime_to_jd(dt)
    return _gmst_from_jd(jd.jd, jd.fr)


def _gmst_from_jd(jd_val: float, fr_val: float) -> float:
    """Compute GMST from Julian Date components (radians)."""
    t_ut1 = (jd_val + fr_val - 2451545.0) / 36525.0
    gmst_sec = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t_ut1
        + 0.093104 * t_ut1 ** 2
        - 6.2e-6 * t_ut1 ** 3
    )
    gmst_rad = (gmst_sec % SECONDS_PER_DAY) / SECONDS_PER_DAY * TWO_PI
    return gmst_rad % TWO_PI


def tle_epoch_to_datetime(epoch_year: int, epoch_day: float) -> datetime:
    """Convert TLE epoch (2-digit year + fractional day-of-year) to datetime.

    Year rule: 0-56 -> 2000-2056; 57-99 -> 1957-1999.
    """
    if epoch_year < 57:
        full_year = 2000 + epoch_year
    else:
        full_year = 1900 + epoch_year

    base = datetime(full_year, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(days=epoch_day - 1.0)


def generate_time_steps(
    start: datetime, end: datetime, step_seconds: float
) -> tuple[np.ndarray, np.ndarray]:
    """Generate arrays of (jd, fr) pairs for vectorized SGP4 propagation.

    Returns two numpy float64 arrays of equal length for use with
    satellite.sgp4_array(jd_array, fr_array).
    """
    start_jd = datetime_to_jd(start)
    total_seconds = (end - start).total_seconds()
    n_steps = max(1, int(total_seconds / step_seconds) + 1)

    offsets_days = np.linspace(0, total_seconds / SECONDS_PER_DAY, n_steps)
    jd_arr = np.full(n_steps, start_jd.jd, dtype=np.float64)
    fr_arr = start_jd.fr + offsets_days

    # Handle fractional overflow past 1.0
    overflow = fr_arr >= 1.0
    if np.any(overflow):
        floor_vals = np.floor(fr_arr[overflow])
        jd_arr[overflow] += floor_vals
        fr_arr[overflow] -= floor_vals

    return jd_arr, fr_arr


def compute_gmst_batch(
    jd_array: np.ndarray, fr_array: np.ndarray
) -> np.ndarray:
    """Compute GMST for an array of Julian dates (vectorized).

    Uses the IAU 1982 analytical GMST model to avoid N astropy calls.
    Returns array of GMST values in radians.
    """
    t_ut1 = (jd_array + fr_array - 2451545.0) / 36525.0
    gmst_sec = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t_ut1
        + 0.093104 * t_ut1 ** 2
        - 6.2e-6 * t_ut1 ** 3
    )
    gmst_rad = (gmst_sec % SECONDS_PER_DAY) / SECONDS_PER_DAY * TWO_PI
    return gmst_rad % TWO_PI


def sun_position_eci(dt: datetime) -> np.ndarray:
    """Approximate Sun position in ECI frame (km) for shadow calculations.

    Uses simplified solar position model accurate to ~1 degree,
    sufficient for umbra/penumbra shadow detection.
    """
    jd = datetime_to_jd(dt)
    t = (jd.full - 2451545.0) / 36525.0

    # Mean longitude of Sun (degrees)
    l0 = (280.46646 + 36000.76983 * t) % 360.0
    # Mean anomaly of Sun (degrees)
    m = (357.52911 + 35999.05029 * t) % 360.0
    m_rad = m * DEG_TO_RAD

    # Equation of center
    c = 1.9146 * math.sin(m_rad) + 0.02 * math.sin(2.0 * m_rad)
    sun_lon = (l0 + c) * DEG_TO_RAD

    # Obliquity of ecliptic
    obliquity = (23.439 - 0.013 * t) * DEG_TO_RAD

    # Distance in AU (approximate)
    dist_au = 1.00014 - 0.01671 * math.cos(m_rad)
    dist_km = dist_au * AU_KM

    # ECI position
    x = dist_km * math.cos(sun_lon)
    y = dist_km * math.sin(sun_lon) * math.cos(obliquity)
    z = dist_km * math.sin(sun_lon) * math.sin(obliquity)
    return np.array([x, y, z])


def sun_position_eci_batch(
    jd_array: np.ndarray, fr_array: np.ndarray
) -> np.ndarray:
    """Vectorized Sun position in ECI frame for batch shadow detection.

    Returns shape (N, 3) array of Sun positions in km.
    For short propagation ranges (<1 day), a single Sun position is
    typically sufficient. This function is provided for longer ranges.
    """
    t = (jd_array + fr_array - 2451545.0) / 36525.0

    l0 = (280.46646 + 36000.76983 * t) % 360.0
    m = (357.52911 + 35999.05029 * t) % 360.0
    m_rad = m * DEG_TO_RAD

    c = 1.9146 * np.sin(m_rad) + 0.02 * np.sin(2.0 * m_rad)
    sun_lon = (l0 + c) * DEG_TO_RAD
    obliquity = (23.439 - 0.013 * t) * DEG_TO_RAD

    dist_km = (1.00014 - 0.01671 * np.cos(m_rad)) * AU_KM

    result = np.empty((len(t), 3))
    result[:, 0] = dist_km * np.cos(sun_lon)
    result[:, 1] = dist_km * np.sin(sun_lon) * np.cos(obliquity)
    result[:, 2] = dist_km * np.sin(sun_lon) * np.sin(obliquity)
    return result
