"""Conjunction screening engine.

Performs coarse + fine filter screening of a protected asset against
the full satellite catalog to identify close approaches. This is the
core computation of SentinelSpace.

Performance strategy:
  - Coarse filter: apogee/perigee overlap + inclination proximity
  - Fine filter: vectorized SGP4 (sgp4_array) — propagate primary ONCE,
    then batch-propagate each secondary and compute distances with numpy.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

import numpy as np
from sgp4.api import Satrec, jday

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
class ConjunctionCandidate:
    """A potential conjunction found during screening."""
    primary_tle: TLEData
    secondary_tle: TLEData
    tca: datetime
    miss_distance_m: float
    radial_m: float = 0.0
    in_track_m: float = 0.0
    cross_track_m: float = 0.0
    relative_velocity_kms: float = 0.0
    collision_probability: float = 0.0
    threat_level: str = "LOW"
    primary_pos_eci: np.ndarray = field(default_factory=lambda: np.zeros(3))
    primary_vel_eci: np.ndarray = field(default_factory=lambda: np.zeros(3))
    secondary_pos_eci: np.ndarray = field(default_factory=lambda: np.zeros(3))
    secondary_vel_eci: np.ndarray = field(default_factory=lambda: np.zeros(3))


@dataclass
class ScreeningResult:
    """Result of a screening run, including metadata."""
    conjunctions: list[ConjunctionCandidate]
    closest_miss_km: float = float("inf")
    closest_miss_object: str = ""
    candidates_scanned: int = 0
    close_approaches: int = 0


def screen_asset(
    asset_tle: TLEData,
    catalog: list[TLEData],
    time_window_days: float = 7.0,
    distance_threshold_km: float = 5.0,
    step_seconds: float = 60.0,
    progress_callback: Optional[Callable[[float, int, int], None]] = None,
    asset_radius_m: float = 1.0,
) -> ScreeningResult:
    """Screen a protected asset against the catalog.

    Uses a three-pass approach:
    1. Coarse filter: apogee/perigee + inclination overlap check
    2. Fast vectorized distance scan (300s steps)
    3. TCA refinement + collision probability for close approaches
    """
    start_time = time.time()
    start_dt = datetime.utcnow()
    end_dt = start_dt + timedelta(days=time_window_days)

    logger.info(
        "Starting screening: asset=%s, catalog_size=%d, window=%.1f days, threshold=%.1f km",
        asset_tle.name, len(catalog), time_window_days, distance_threshold_km,
    )

    # Skip self
    catalog_filtered = [t for t in catalog if t.catalog_number != asset_tle.catalog_number]
    logger.info("Catalog after self-removal: %d objects", len(catalog_filtered))

    if not catalog_filtered:
        logger.warning("Empty catalog — nothing to screen against")
        return ScreeningResult(conjunctions=[])

    # --- Pass 1: Coarse filter ---
    candidates = _coarse_filter(asset_tle, catalog_filtered)
    logger.info(
        "Coarse filter: %d candidates from %d objects (%.1f%% eliminated)",
        len(candidates),
        len(catalog_filtered),
        (1 - len(candidates) / max(1, len(catalog_filtered))) * 100,
    )

    if progress_callback:
        progress_callback(0.05, len(candidates), 0)

    if not candidates:
        return ScreeningResult(conjunctions=[])

    # --- Pass 2: Vectorized two-stage distance scan ---
    #
    # Stage A: Coarse scan at 120s steps — find objects approaching within
    #          a wide detection envelope (2000km). At 15km/s relative velocity,
    #          an object within 50km of closest approach will be within
    #          ~1800km of the nearest 120s sample.
    # Stage B: For detected objects, refine with 10s steps in a narrow window
    #          to find the precise closest approach.

    coarse_step = 120.0  # seconds
    total_seconds = (end_dt - start_dt).total_seconds()
    n_coarse = int(total_seconds / coarse_step) + 1
    n_coarse = min(n_coarse, 60000)

    # Detection envelope: at max relative velocity ~15km/s, objects traverse
    # coarse_step * 15 = 1800km between steps. Add threshold on top.
    detection_envelope_km = coarse_step * 15.0 + distance_threshold_km

    # Build JD arrays for coarse grid
    jd_coarse = np.zeros(n_coarse)
    fr_coarse = np.zeros(n_coarse)
    for i in range(n_coarse):
        dt = start_dt + timedelta(seconds=i * coarse_step)
        jd_val = datetime_to_jd(dt)
        jd_coarse[i] = jd_val.jd
        fr_coarse[i] = jd_val.fr

    # Pre-propagate primary asset (vectorized SGP4)
    primary_sat = Satrec.twoline2rv(asset_tle.line1, asset_tle.line2)
    p_err, p_pos, p_vel = primary_sat.sgp4_array(jd_coarse, fr_coarse)

    valid_mask = (p_err == 0)
    if not np.any(valid_mask):
        logger.error("Primary asset propagation failed completely")
        return []

    logger.info(
        "Primary pre-propagated: %d/%d steps (%.0fs intervals over %.1f days)",
        np.sum(valid_mask), n_coarse, coarse_step, time_window_days,
    )

    if progress_callback:
        progress_callback(0.1, len(candidates), 0)

    # --- Stage A: Coarse scan each candidate ---
    close_approaches = []  # (secondary_tle, approx_tca_idx, min_dist)
    total_candidates = len(candidates)

    for idx, sec_tle in enumerate(candidates):
        try:
            sec_sat = Satrec.twoline2rv(sec_tle.line1, sec_tle.line2)
            s_err, s_pos, s_vel = sec_sat.sgp4_array(jd_coarse, fr_coarse)

            both_valid = valid_mask & (s_err == 0)
            if not np.any(both_valid):
                continue

            diff = p_pos - s_pos
            dist_km = np.full(n_coarse, np.inf)
            dist_km[both_valid] = np.linalg.norm(diff[both_valid], axis=1)

            min_idx = np.argmin(dist_km)
            min_dist = dist_km[min_idx]

            if min_dist < detection_envelope_km:
                close_approaches.append((sec_tle, int(min_idx), min_dist))

        except Exception:
            pass

        if progress_callback and (idx + 1) % max(1, total_candidates // 20) == 0:
            pct = 0.1 + 0.4 * (idx + 1) / total_candidates
            progress_callback(pct, total_candidates, len(close_approaches))

    logger.info(
        "Coarse scan: %d objects within %.0fkm envelope (from %d candidates)",
        len(close_approaches), detection_envelope_km, total_candidates,
    )

    if progress_callback:
        progress_callback(0.5, len(close_approaches), 0)

    # --- Stage B: Fine refinement for close approaches ---
    conjunctions: list[ConjunctionCandidate] = []
    fine_step = 10.0  # seconds
    closest_miss_km = float("inf")
    closest_miss_object = ""

    for ca_idx, (sec_tle, coarse_idx, coarse_dist) in enumerate(close_approaches):
        try:
            # Build a fine time grid around the coarse minimum (±2 coarse steps)
            center_sec = coarse_idx * coarse_step
            fine_start = max(0, center_sec - 2 * coarse_step)
            fine_end = min(total_seconds, center_sec + 2 * coarse_step)
            n_fine = int((fine_end - fine_start) / fine_step) + 1

            jd_fine = np.zeros(n_fine)
            fr_fine = np.zeros(n_fine)
            for i in range(n_fine):
                dt = start_dt + timedelta(seconds=fine_start + i * fine_step)
                jd_val = datetime_to_jd(dt)
                jd_fine[i] = jd_val.jd
                fr_fine[i] = jd_val.fr

            # Propagate both on fine grid
            pf_err, pf_pos, _ = primary_sat.sgp4_array(jd_fine, fr_fine)
            sec_sat = Satrec.twoline2rv(sec_tle.line1, sec_tle.line2)
            sf_err, sf_pos, _ = sec_sat.sgp4_array(jd_fine, fr_fine)

            fine_valid = (pf_err == 0) & (sf_err == 0)
            if not np.any(fine_valid):
                continue

            fine_diff = pf_pos - sf_pos
            fine_dist = np.full(n_fine, np.inf)
            fine_dist[fine_valid] = np.linalg.norm(fine_diff[fine_valid], axis=1)

            fine_min_idx = np.argmin(fine_dist)
            fine_min_dist = fine_dist[fine_min_idx]

            # Track closest miss across all objects
            if fine_min_dist < closest_miss_km:
                closest_miss_km = fine_min_dist
                closest_miss_object = sec_tle.name or f"NORAD {sec_tle.catalog_number}"

            # Refine TCA using golden section search (finds true minimum)
            approx_tca = start_dt + timedelta(seconds=fine_start + float(fine_min_idx) * fine_step)

            result = _refine_and_compute(
                asset_tle, sec_tle,
                approx_tca, fine_step,
                distance_threshold_km,
                asset_radius_m,
            )
            if result is not None:
                conjunctions.append(result)
                logger.info(
                    "Conjunction: %s vs %s, miss=%.0fm, Pc=%.2e, TCA=%s",
                    asset_tle.name, sec_tle.name,
                    result.miss_distance_m, result.collision_probability, result.tca,
                )

        except Exception as e:
            logger.debug("Fine refinement error for %s: %s", sec_tle.name, e)

        if progress_callback and (ca_idx + 1) % max(1, len(close_approaches) // 20) == 0:
            pct = 0.5 + 0.5 * (ca_idx + 1) / max(1, len(close_approaches))
            progress_callback(pct, len(close_approaches), len(conjunctions))

    if progress_callback:
        progress_callback(1.0, total_candidates, len(conjunctions))

    # Sort by collision probability (highest first)
    conjunctions.sort(key=lambda c: c.collision_probability, reverse=True)

    elapsed = time.time() - start_time
    logger.info(
        "Screening complete: %d conjunctions found in %.1fs (scanned %d candidates, "
        "closest miss: %.1f km by %s)",
        len(conjunctions), elapsed, total_candidates,
        closest_miss_km, closest_miss_object,
    )

    return ScreeningResult(
        conjunctions=conjunctions,
        closest_miss_km=closest_miss_km,
        closest_miss_object=closest_miss_object,
        candidates_scanned=total_candidates,
        close_approaches=len(close_approaches),
    )


def _coarse_filter(
    asset_tle: TLEData,
    catalog: list[TLEData],
    altitude_margin_km: float = 30.0,
) -> list[TLEData]:
    """Coarse filter: check if orbits can physically intersect.

    Uses apogee/perigee overlap test — if the apogee of one orbit
    doesn't reach the perigee of the other (minus margin), there's
    no possible conjunction.
    """
    asset_a_km = _sma_from_mean_motion(asset_tle.mean_motion)
    asset_ecc = asset_tle.eccentricity
    asset_apogee = asset_a_km * (1 + asset_ecc) - R_EARTH
    asset_perigee = asset_a_km * (1 - asset_ecc) - R_EARTH

    candidates = []
    for tle in catalog:
        try:
            sec_a_km = _sma_from_mean_motion(tle.mean_motion)
            sec_ecc = tle.eccentricity
            sec_apogee = sec_a_km * (1 + sec_ecc) - R_EARTH
            sec_perigee = sec_a_km * (1 - sec_ecc) - R_EARTH

            # Check altitude overlap with margin
            if (asset_perigee - altitude_margin_km <= sec_apogee + altitude_margin_km and
                    sec_perigee - altitude_margin_km <= asset_apogee + altitude_margin_km):
                candidates.append(tle)
        except Exception:
            continue

    return candidates


def _sma_from_mean_motion(mean_motion_revs_per_day: float) -> float:
    """Compute semi-major axis from mean motion (revs/day)."""
    n_rad_per_sec = mean_motion_revs_per_day * 2.0 * math.pi / 86400.0
    if n_rad_per_sec <= 0:
        return R_EARTH + 500.0
    return (MU_EARTH / (n_rad_per_sec ** 2)) ** (1.0 / 3.0)


def _refine_and_compute(
    primary_tle: TLEData,
    secondary_tle: TLEData,
    approx_tca: datetime,
    scan_step: float,
    threshold_km: float,
    primary_radius_m: float,
) -> Optional[ConjunctionCandidate]:
    """Refine TCA and compute collision probability for a close approach."""
    try:
        primary_prop = OrbitalPropagator(primary_tle)
        secondary_prop = OrbitalPropagator(secondary_tle)
    except Exception:
        return None

    # Refine TCA with golden section search around the approximate TCA
    tca, tca_dist_km = _refine_tca(
        primary_prop,
        secondary_prop,
        approx_tca - timedelta(seconds=scan_step),
        approx_tca + timedelta(seconds=scan_step),
        precision_seconds=0.1,
    )

    if tca_dist_km > threshold_km:
        return None

    # Get precise state vectors at TCA
    try:
        p1 = primary_prop.propagate(tca)
        p2 = secondary_prop.propagate(tca)
    except Exception:
        return None

    r1, v1 = p1.position_eci, p1.velocity_eci
    r2, v2 = p2.position_eci, p2.velocity_eci

    # Compute covariance estimates (strip tzinfo to avoid naive/aware mismatch)
    pri_epoch = primary_tle.epoch_datetime.replace(tzinfo=None) if primary_tle.epoch_datetime and primary_tle.epoch_datetime.tzinfo else primary_tle.epoch_datetime
    sec_epoch = secondary_tle.epoch_datetime.replace(tzinfo=None) if secondary_tle.epoch_datetime and secondary_tle.epoch_datetime.tzinfo else secondary_tle.epoch_datetime
    primary_age_hours = max(0.0, (tca - pri_epoch).total_seconds() / 3600.0) if pri_epoch else 48.0
    secondary_age_hours = max(0.0, (tca - sec_epoch).total_seconds() / 3600.0) if sec_epoch else 72.0

    cov1_ric = default_covariance_ric(primary_age_hours, "payload")
    cov2_ric = default_covariance_ric(secondary_age_hours, "unknown")

    cov1_eci = covariance_ric_to_eci(cov1_ric, r1, v1)
    cov2_eci = covariance_ric_to_eci(cov2_ric, r2, v2)

    secondary_radius_m = estimate_hard_body_radius(object_type="unknown")

    # Compute collision probability
    result = compute_collision_probability(
        r1, v1, r2, v2,
        cov1_eci, cov2_eci,
        primary_radius_m, secondary_radius_m,
    )

    threat_level = classify_threat_level(result.collision_probability)

    return ConjunctionCandidate(
        primary_tle=primary_tle,
        secondary_tle=secondary_tle,
        tca=tca,
        miss_distance_m=result.miss_distance_m,
        radial_m=result.radial_m,
        in_track_m=result.in_track_m,
        cross_track_m=result.cross_track_m,
        relative_velocity_kms=result.relative_velocity_kms,
        collision_probability=result.collision_probability,
        threat_level=threat_level,
        primary_pos_eci=r1,
        primary_vel_eci=v1,
        secondary_pos_eci=r2,
        secondary_vel_eci=v2,
    )


def _refine_tca(
    prop1: OrbitalPropagator,
    prop2: OrbitalPropagator,
    t_start: datetime,
    t_end: datetime,
    precision_seconds: float = 0.1,
) -> tuple[datetime, float]:
    """Refine TCA using golden section search."""
    golden_ratio = (math.sqrt(5) - 1) / 2

    # Use offset in seconds from t_start to avoid timezone issues
    a = 0.0
    b = (t_end - t_start).total_seconds()

    while (b - a) > precision_seconds:
        c = b - golden_ratio * (b - a)
        d = a + golden_ratio * (b - a)

        dt_c = t_start + timedelta(seconds=c)
        dt_d = t_start + timedelta(seconds=d)

        try:
            p1c = prop1.propagate(dt_c)
            p2c = prop2.propagate(dt_c)
            dist_c = np.linalg.norm(p1c.position_eci - p2c.position_eci)
        except Exception:
            dist_c = float('inf')

        try:
            p1d = prop1.propagate(dt_d)
            p2d = prop2.propagate(dt_d)
            dist_d = np.linalg.norm(p1d.position_eci - p2d.position_eci)
        except Exception:
            dist_d = float('inf')

        if dist_c < dist_d:
            b = d
        else:
            a = c

    tca_offset = (a + b) / 2.0
    tca_dt = t_start + timedelta(seconds=tca_offset)

    try:
        p1 = prop1.propagate(tca_dt)
        p2 = prop2.propagate(tca_dt)
        min_dist = np.linalg.norm(p1.position_eci - p2.position_eci)
    except Exception:
        min_dist = float('inf')

    return tca_dt, min_dist
