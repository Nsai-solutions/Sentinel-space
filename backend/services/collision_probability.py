"""Foster/Alfano 2D collision probability computation.

Implements the standard 2D probability of collision (Pc) method used
in operational conjunction assessment. Projects the encounter geometry
onto the conjunction plane (perpendicular to relative velocity) and
integrates a 2D Gaussian over the combined hard-body circle.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollisionResult:
    """Result of a collision probability computation."""
    collision_probability: float
    miss_distance_m: float
    radial_m: float
    in_track_m: float
    cross_track_m: float
    relative_velocity_kms: float
    combined_hard_body_radius_m: float
    conjunction_plane_miss: tuple[float, float]  # (x, y) in conjunction plane


def compute_collision_probability(
    r1: np.ndarray,
    v1: np.ndarray,
    r2: np.ndarray,
    v2: np.ndarray,
    cov1: np.ndarray,
    cov2: np.ndarray,
    radius1: float,
    radius2: float,
) -> CollisionResult:
    """Compute 2D collision probability using Foster/Alfano method.

    Args:
        r1, r2: Position vectors (ECI, km) of primary and secondary objects.
        v1, v2: Velocity vectors (ECI, km/s) of primary and secondary objects.
        cov1, cov2: 3x3 position covariance matrices (km^2) in ECI frame.
        radius1, radius2: Hard-body radii (meters) of primary and secondary.

    Returns:
        CollisionResult with probability and geometry details.
    """
    # Relative state
    delta_r = (r2 - r1) * 1000.0  # km -> meters
    delta_v = (v2 - v1) * 1000.0  # km/s -> m/s
    rel_vel_mag = np.linalg.norm(delta_v)

    if rel_vel_mag < 1e-6:
        return CollisionResult(
            collision_probability=0.0,
            miss_distance_m=np.linalg.norm(delta_r),
            radial_m=0.0, in_track_m=0.0, cross_track_m=0.0,
            relative_velocity_kms=0.0,
            combined_hard_body_radius_m=radius1 + radius2,
            conjunction_plane_miss=(0.0, 0.0),
        )

    miss_distance_m = np.linalg.norm(delta_r)

    # Decompose miss distance into radial, in-track, cross-track
    ric = _decompose_miss_distance_ric(r1 * 1000.0, v1 * 1000.0, delta_r)

    # Build conjunction plane basis (perpendicular to relative velocity)
    e_along = delta_v / rel_vel_mag

    # Find two orthogonal vectors in the conjunction plane
    if abs(e_along[2]) < 0.9:
        temp = np.array([0.0, 0.0, 1.0])
    else:
        temp = np.array([1.0, 0.0, 0.0])

    e_x = np.cross(e_along, temp)
    e_x /= np.linalg.norm(e_x)
    e_y = np.cross(e_along, e_x)
    e_y /= np.linalg.norm(e_y)

    # Rotation matrix from ECI to conjunction plane
    R = np.vstack([e_x, e_y])  # 2x3

    # Project miss distance onto conjunction plane
    miss_2d = R @ delta_r  # 2-vector (meters)

    # Combined covariance in ECI (convert km^2 to m^2)
    cov_combined = (cov1 + cov2) * 1e6

    # Project covariance onto conjunction plane
    cov_2d = R @ cov_combined @ R.T  # 2x2

    # Combined hard-body radius
    combined_radius = radius1 + radius2

    # Compute collision probability
    pc = _alfano_2d_pc(miss_2d, cov_2d, combined_radius)

    return CollisionResult(
        collision_probability=pc,
        miss_distance_m=miss_distance_m,
        radial_m=ric[0],
        in_track_m=ric[1],
        cross_track_m=ric[2],
        relative_velocity_kms=rel_vel_mag / 1000.0,
        combined_hard_body_radius_m=combined_radius,
        conjunction_plane_miss=(float(miss_2d[0]), float(miss_2d[1])),
    )


def _decompose_miss_distance_ric(
    r_primary: np.ndarray,
    v_primary: np.ndarray,
    delta_r: np.ndarray,
) -> tuple[float, float, float]:
    """Decompose miss distance into Radial, In-track, Cross-track components.

    Uses the RSW (radial, along-track, cross-track) frame of the primary object.
    """
    r_mag = np.linalg.norm(r_primary)
    if r_mag < 1e-10:
        return (0.0, 0.0, 0.0)

    # Radial direction
    e_r = r_primary / r_mag

    # Cross-track (angular momentum direction)
    h = np.cross(r_primary, v_primary)
    h_mag = np.linalg.norm(h)
    if h_mag < 1e-10:
        return (float(np.linalg.norm(delta_r)), 0.0, 0.0)

    e_c = h / h_mag

    # In-track (completes right-handed system)
    e_i = np.cross(e_c, e_r)

    radial = float(np.dot(delta_r, e_r))
    in_track = float(np.dot(delta_r, e_i))
    cross_track = float(np.dot(delta_r, e_c))

    return (radial, in_track, cross_track)


def _alfano_2d_pc(
    miss_2d: np.ndarray,
    cov_2d: np.ndarray,
    hard_body_radius: float,
    n_terms: int = 30,
) -> float:
    """Compute 2D Pc using Alfano's series expansion.

    Integrates the 2D Gaussian probability density over a circle of
    radius `hard_body_radius` centered at the projected miss distance.

    Uses the Rice distribution formulation:
    Pc = 1 - exp(-R²/(2σ²)) for the circular case, extended to
    the elliptical case via Alfano's series.

    Args:
        miss_2d: 2D miss distance vector in conjunction plane (meters).
        cov_2d: 2x2 covariance matrix in conjunction plane (m^2).
        hard_body_radius: Combined hard-body radius (meters).
        n_terms: Number of terms in series expansion.

    Returns:
        Collision probability (dimensionless, 0 to 1).
    """
    # Eigendecompose the 2D covariance to get principal axes
    eigenvalues, eigenvectors = np.linalg.eigh(cov_2d)

    # Ensure positive eigenvalues (minimum 100 m² = 10m sigma)
    sigma_x_sq = max(eigenvalues[0], 100.0)
    sigma_y_sq = max(eigenvalues[1], 100.0)

    # Rotate miss distance into principal axes
    miss_rotated = eigenvectors.T @ miss_2d
    xm = miss_rotated[0]
    ym = miss_rotated[1]

    R = hard_body_radius

    # Normalize by geometric mean of sigmas
    sigma_x = math.sqrt(sigma_x_sq)
    sigma_y = math.sqrt(sigma_y_sq)

    # Use the direct numerical integration approach (Foster's method)
    # For the integral of the 2D Gaussian over the hard-body circle
    pc = _foster_integration(xm, ym, sigma_x, sigma_y, R)

    return max(0.0, min(1.0, pc))


def _foster_integration(
    xm: float,
    ym: float,
    sigma_x: float,
    sigma_y: float,
    R: float,
    n_steps: int = 200,
) -> float:
    """Foster's numerical integration method for 2D Pc.

    Integrates the bivariate Gaussian over the hard-body circle
    using angular decomposition.
    """
    if sigma_x < 1e-10 or sigma_y < 1e-10:
        return 0.0

    pc = 0.0
    d_theta = 2.0 * math.pi / n_steps

    for i in range(n_steps):
        theta = (i + 0.5) * d_theta

        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        # Point on the hard-body circle boundary
        x = xm + R * cos_t
        y = ym + R * sin_t

        # Gaussian PDF value at this point
        exponent = -0.5 * ((x / sigma_x) ** 2 + (y / sigma_y) ** 2)
        if exponent > -500:
            pdf = math.exp(exponent) / (2.0 * math.pi * sigma_x * sigma_y)
        else:
            pdf = 0.0

        # Contribution: area element = R * d_theta * R/2 (trapezoidal from center)
        pc += pdf

    # Area element for each angular step: dA = (R^2 / 2) * d_theta
    # (integration in polar coordinates centered on circle center)
    pc *= (R ** 2 / 2.0) * d_theta

    # Better approach: use the exact formula via series expansion
    # The above is a rough estimate; refine with proper integration
    pc_refined = _integrate_gaussian_over_circle(xm, ym, sigma_x, sigma_y, R)

    return pc_refined


def _integrate_gaussian_over_circle(
    xm: float,
    ym: float,
    sigma_x: float,
    sigma_y: float,
    R: float,
    n_radial: int = 50,
    n_angular: int = 100,
) -> float:
    """Integrate bivariate Gaussian over a circle using polar quadrature.

    Uses Gauss-Legendre quadrature in the radial direction and uniform
    spacing in the angular direction for accurate numerical integration.
    """
    if sigma_x < 1e-10 or sigma_y < 1e-10:
        return 0.0

    # Gauss-Legendre quadrature points for radial direction [0, R]
    from numpy.polynomial.legendre import leggauss
    nodes, weights = leggauss(n_radial)

    # Map from [-1, 1] to [0, R]
    r_nodes = 0.5 * R * (nodes + 1.0)
    r_weights = 0.5 * R * weights

    inv_2sx2 = 0.5 / (sigma_x ** 2)
    inv_2sy2 = 0.5 / (sigma_y ** 2)
    norm_factor = 1.0 / (2.0 * math.pi * sigma_x * sigma_y)

    d_theta = 2.0 * math.pi / n_angular
    theta_angles = np.linspace(0.5 * d_theta, 2.0 * math.pi - 0.5 * d_theta, n_angular)
    cos_t = np.cos(theta_angles)
    sin_t = np.sin(theta_angles)

    total = 0.0
    for i in range(n_radial):
        r = r_nodes[i]
        w_r = r_weights[i]

        # Points on circle at radius r
        x_arr = xm + r * cos_t
        y_arr = ym + r * sin_t

        exponents = -(x_arr ** 2) * inv_2sx2 - (y_arr ** 2) * inv_2sy2
        # Clip to avoid underflow
        valid = exponents > -500
        pdf_sum = np.sum(np.exp(exponents[valid]))

        # Angular integration * radial weight * r (Jacobian)
        total += pdf_sum * d_theta * w_r * r

    total *= norm_factor

    return float(total)


def classify_threat_level(pc: float) -> str:
    """Classify collision probability into threat level.

    CRITICAL: Pc > 1e-3
    HIGH:     1e-4 < Pc <= 1e-3
    MODERATE: 1e-5 < Pc <= 1e-4
    LOW:      Pc <= 1e-5
    """
    if pc > 1e-3:
        return "CRITICAL"
    elif pc > 1e-4:
        return "HIGH"
    elif pc > 1e-5:
        return "MODERATE"
    else:
        return "LOW"


def run_monte_carlo(
    r1: np.ndarray,
    v1: np.ndarray,
    r2: np.ndarray,
    v2: np.ndarray,
    cov1: np.ndarray,
    cov2: np.ndarray,
    radius1: float,
    radius2: float,
    n_samples: int = 10000,
) -> dict:
    """Monte Carlo collision probability estimation.

    Draws N samples from the combined position uncertainty and
    checks how many result in distances less than the combined radius.

    Returns dict with probability, confidence interval, and distribution.
    """
    combined_radius = radius1 + radius2
    combined_radius_km = combined_radius / 1000.0

    # Nominal miss distance
    delta_r_km = r2 - r1

    # Combined covariance (km^2)
    cov_combined = cov1 + cov2

    # Draw samples from multivariate normal
    rng = np.random.default_rng()
    try:
        samples = rng.multivariate_normal(delta_r_km, cov_combined, size=n_samples)
    except np.linalg.LinAlgError:
        # If covariance is singular, add small diagonal
        cov_fixed = cov_combined + np.eye(3) * 1e-12
        samples = rng.multivariate_normal(delta_r_km, cov_fixed, size=n_samples)

    # Compute distances for all samples
    distances_km = np.linalg.norm(samples, axis=1)
    distances_m = distances_km * 1000.0

    # Count collisions
    collisions = np.sum(distances_km < combined_radius_km)
    pc_mc = collisions / n_samples

    # Wilson confidence interval
    z = 1.96  # 95% confidence
    n = n_samples
    p_hat = pc_mc
    denom = 1 + z ** 2 / n
    center = (p_hat + z ** 2 / (2 * n)) / denom
    half_width = z * math.sqrt((p_hat * (1 - p_hat) + z ** 2 / (4 * n)) / n) / denom
    ci_lower = max(0.0, center - half_width)
    ci_upper = min(1.0, center + half_width)

    # Distance distribution percentiles
    dist_percentiles = {
        "p5": float(np.percentile(distances_m, 5)),
        "p25": float(np.percentile(distances_m, 25)),
        "p50": float(np.percentile(distances_m, 50)),
        "p75": float(np.percentile(distances_m, 75)),
        "p95": float(np.percentile(distances_m, 95)),
        "min": float(np.min(distances_m)),
        "max": float(np.max(distances_m)),
        "mean": float(np.mean(distances_m)),
        "std": float(np.std(distances_m)),
    }

    return {
        "collision_probability": pc_mc,
        "n_samples": n_samples,
        "n_collisions": int(collisions),
        "confidence_interval": [ci_lower, ci_upper],
        "distance_distribution": dist_percentiles,
    }
