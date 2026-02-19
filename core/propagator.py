"""SGP4-based orbital propagation engine.

Wraps the sgp4 library to provide high-level propagation with
automatic coordinate conversion, shadow detection, and batch
operations for orbit trail generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
from sgp4.api import Satrec, WGS72

from core.coordinate_transforms import (
    ecef_to_geodetic,
    ecef_to_geodetic_batch,
    eci_to_ecef,
    eci_to_ecef_batch,
)
from core.orbital_mechanics import classify_orbit, state_vectors_to_elements
from core.tle_parser import TLEData
from utils.constants import (
    R_EARTH,
    R_EARTH_EQUATORIAL,
    SECONDS_PER_DAY,
    TWO_PI,
    MU_EARTH,
)
from utils.time_utils import (
    compute_gmst_batch,
    datetime_to_gmst,
    datetime_to_jd,
    generate_time_steps,
    sun_position_eci,
)

logger = logging.getLogger(__name__)


class PropagationError(Exception):
    """Raised when SGP4 propagation fails."""

    def __init__(
        self, message: str, error_code: int = 0, satellite_name: str = ""
    ):
        self.error_code = error_code
        self.satellite_name = satellite_name
        super().__init__(message)

    @staticmethod
    def error_message(code: int) -> str:
        messages = {
            1: "Mean elements: eccentricity >= 1.0 or < -0.001 or a < 0.95",
            2: "Mean motion less than 0.0",
            3: "Perturbed eccentricity < 0.0 or > 1.0",
            4: "Semi-latus rectum < 0.0",
            5: "Epoch elements are sub-orbital",
            6: "Satellite has decayed",
        }
        return messages.get(code, f"Unknown SGP4 error code {code}")


@dataclass(frozen=True, slots=True)
class PropagationResult:
    """Complete state of a satellite at a single instant."""

    datetime_utc: datetime
    position_eci: np.ndarray  # [x, y, z] km
    velocity_eci: np.ndarray  # [vx, vy, vz] km/s
    latitude: float  # degrees [-90, 90]
    longitude: float  # degrees [-180, 180]
    altitude: float  # km above WGS84 ellipsoid
    speed: float  # km/s
    in_shadow: bool


@dataclass(frozen=True, slots=True)
class OrbitalElements:
    """Osculating Keplerian elements at a given instant."""

    semi_major_axis: float  # km
    eccentricity: float
    inclination: float  # degrees
    raan: float  # degrees
    arg_perigee: float  # degrees
    true_anomaly: float  # degrees
    period: float  # seconds
    apogee_altitude: float  # km
    perigee_altitude: float  # km
    orbit_type: str
    specific_energy: float  # km^2/s^2
    angular_momentum: float  # km^2/s
    velocity: float  # km/s


@dataclass(frozen=True, slots=True)
class GroundTrackPoint:
    """A single point on a satellite's ground track."""

    datetime_utc: datetime
    latitude: float  # degrees
    longitude: float  # degrees
    altitude: float  # km
    in_shadow: bool


class OrbitalPropagator:
    """SGP4-based orbital propagation engine."""

    def __init__(self, tle_data: TLEData):
        """Initialize SGP4 satellite object from TLE data."""
        self._tle = tle_data
        self._satellite = Satrec.twoline2rv(tle_data.line1, tle_data.line2)

        if self._satellite.error != 0:
            raise PropagationError(
                f"SGP4 init failed for {tle_data.name}: "
                f"{PropagationError.error_message(self._satellite.error)}",
                error_code=self._satellite.error,
                satellite_name=tle_data.name,
            )

    @property
    def tle(self) -> TLEData:
        return self._tle

    @property
    def satellite(self) -> Satrec:
        return self._satellite

    def propagate(self, dt: datetime) -> PropagationResult:
        """Propagate to a single datetime."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        jd = datetime_to_jd(dt)
        error, r_tuple, v_tuple = self._satellite.sgp4(jd.jd, jd.fr)

        if error != 0:
            raise PropagationError(
                f"SGP4 propagation failed for {self._tle.name}: "
                f"{PropagationError.error_message(error)}",
                error_code=error,
                satellite_name=self._tle.name,
            )

        pos_eci = np.array(r_tuple)
        vel_eci = np.array(v_tuple)

        # Convert to geodetic
        gmst = datetime_to_gmst(dt)
        pos_ecef = eci_to_ecef(pos_eci, gmst)
        lat, lon, alt = ecef_to_geodetic(pos_ecef)

        speed = float(np.linalg.norm(vel_eci))
        in_shadow = self._is_in_shadow(pos_eci, dt)

        return PropagationResult(
            datetime_utc=dt,
            position_eci=pos_eci,
            velocity_eci=vel_eci,
            latitude=lat,
            longitude=lon,
            altitude=alt,
            speed=speed,
            in_shadow=in_shadow,
        )

    def propagate_range(
        self,
        start: datetime,
        end: datetime,
        step_seconds: float = 60.0,
    ) -> list[PropagationResult]:
        """Batch propagation using numpy vectorization.

        Performance-critical path for orbit trail generation.
        """
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        jd_arr, fr_arr = generate_time_steps(start, end, step_seconds)
        n = len(jd_arr)

        # Vectorized SGP4 propagation (C-accelerated)
        errors, positions, velocities = self._satellite.sgp4_array(jd_arr, fr_arr)

        # Mask out failed points
        valid = errors == 0
        n_valid = np.sum(valid)
        if n_valid == 0:
            logger.warning(
                "All propagation points failed for %s", self._tle.name
            )
            return []

        if n_valid < n:
            logger.warning(
                "%d/%d propagation points failed for %s",
                n - n_valid,
                n,
                self._tle.name,
            )

        # Get valid data
        valid_pos = positions[valid]
        valid_vel = velocities[valid]
        valid_jd = jd_arr[valid]
        valid_fr = fr_arr[valid]

        # Vectorized GMST computation
        gmst_arr = compute_gmst_batch(valid_jd, valid_fr)

        # Vectorized ECI -> ECEF -> Geodetic
        ecef_arr = eci_to_ecef_batch(valid_pos, gmst_arr)
        lats, lons, alts = ecef_to_geodetic_batch(ecef_arr)

        # Speed
        speeds = np.linalg.norm(valid_vel, axis=1)

        # Shadow detection (use single sun position for efficiency)
        mid_jd = datetime_to_jd(start + (end - start) / 2)
        from utils.time_utils import jd_to_datetime
        mid_dt = jd_to_datetime(mid_jd)
        sun_pos = sun_position_eci(mid_dt)
        shadows = self._is_in_shadow_batch(valid_pos, sun_pos)

        # Build results
        results: list[PropagationResult] = []
        total_seconds = (end - start).total_seconds()
        step_count = n_valid

        for i in range(n_valid):
            # Compute datetime for this step
            frac = i / max(1, step_count - 1) if step_count > 1 else 0
            dt_i = start + timedelta(seconds=frac * total_seconds)

            results.append(
                PropagationResult(
                    datetime_utc=dt_i,
                    position_eci=valid_pos[i].copy(),
                    velocity_eci=valid_vel[i].copy(),
                    latitude=float(lats[i]),
                    longitude=float(lons[i]),
                    altitude=float(alts[i]),
                    speed=float(speeds[i]),
                    in_shadow=bool(shadows[i]),
                )
            )

        return results

    def get_orbital_elements(self, dt: datetime) -> OrbitalElements:
        """Compute osculating Keplerian elements from state vectors."""
        result = self.propagate(dt)
        elements = state_vectors_to_elements(
            result.position_eci, result.velocity_eci
        )

        return OrbitalElements(
            semi_major_axis=elements["semi_major_axis"],
            eccentricity=elements["eccentricity"],
            inclination=elements["inclination"],
            raan=elements["raan"],
            arg_perigee=elements["arg_perigee"],
            true_anomaly=elements["true_anomaly"],
            period=elements["period"],
            apogee_altitude=elements["apogee_alt"],
            perigee_altitude=elements["perigee_alt"],
            orbit_type=elements["orbit_type"],
            specific_energy=elements["specific_energy"],
            angular_momentum=elements["angular_momentum"],
            velocity=elements["velocity"],
        )

    def get_ground_track(
        self,
        start: datetime,
        periods: float = 1.0,
        steps: int = 360,
    ) -> list[GroundTrackPoint]:
        """Generate lat/lon ground track for N orbital periods."""
        period_s = self._tle.orbital_period_seconds
        duration = period_s * periods
        step_seconds = duration / max(1, steps)
        end = start + timedelta(seconds=duration)

        results = self.propagate_range(start, end, step_seconds)

        return [
            GroundTrackPoint(
                datetime_utc=r.datetime_utc,
                latitude=r.latitude,
                longitude=r.longitude,
                altitude=r.altitude,
                in_shadow=r.in_shadow,
            )
            for r in results
        ]

    def _is_in_shadow(self, position_eci: np.ndarray, dt: datetime) -> bool:
        """Cylindrical Earth shadow model for a single point."""
        sun_pos = sun_position_eci(dt)
        sun_hat = sun_pos / np.linalg.norm(sun_pos)

        proj = np.dot(position_eci, sun_hat)
        if proj > 0:
            return False

        perp = position_eci - proj * sun_hat
        perp_dist = np.linalg.norm(perp)
        return perp_dist < R_EARTH

    def _is_in_shadow_batch(
        self, positions_eci: np.ndarray, sun_pos: np.ndarray
    ) -> np.ndarray:
        """Vectorized shadow check for N positions."""
        sun_hat = sun_pos / np.linalg.norm(sun_pos)
        proj = positions_eci @ sun_hat
        perp = positions_eci - np.outer(proj, sun_hat)
        perp_dist = np.linalg.norm(perp, axis=1)
        return (proj <= 0) & (perp_dist < R_EARTH)
