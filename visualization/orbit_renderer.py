"""Orbit trail rendering for multiple satellites.

Renders full orbit trails as 3D curves with color-coding
by altitude, velocity, or solid color per satellite.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pyvista as pv

from utils.constants import (
    EARTH_RENDER_RADIUS,
    GEO_ALT,
    LEO_MAX_ALT,
    R_EARTH_EQUATORIAL,
    SATELLITE_COLORS,
)

logger = logging.getLogger(__name__)


@dataclass
class OrbitTrail:
    """Data holder for a single orbit trail."""

    sat_id: str
    mesh: Optional[pv.PolyData] = None
    actor: object = None
    points_render: Optional[np.ndarray] = None  # (N, 3) render coords
    points_eci: Optional[np.ndarray] = None  # (N, 3) ECI km
    color: str = "#3B82F6"
    visible: bool = True


class OrbitRenderer:
    """Manages orbit trail rendering for all satellites."""

    def __init__(self, plotter: pv.Plotter):
        self._plotter = plotter
        self._trails: dict[str, OrbitTrail] = {}
        self._color_mode: str = "solid"  # solid, altitude, velocity
        self._ground_tracks: dict[str, object] = {}  # sat_id -> actor

    def add_orbit(
        self,
        sat_id: str,
        trail_points_eci: np.ndarray,
        color: str = "#3B82F6",
        color_index: int = 0,
    ) -> None:
        """Add orbit trail for a satellite.

        Args:
            sat_id: unique satellite identifier
            trail_points_eci: shape (N, 3) ECI positions in km
            color: hex color for solid mode
            color_index: index into SATELLITE_COLORS
        """
        if sat_id in self._trails:
            self.remove_orbit(sat_id)

        actual_color = color or SATELLITE_COLORS[color_index % len(SATELLITE_COLORS)]

        # Convert ECI km to render coordinates (Earth radius = 1.0)
        render_points = trail_points_eci / R_EARTH_EQUATORIAL

        # Create polyline mesh
        mesh = self._create_trail_mesh(render_points)

        trail = OrbitTrail(
            sat_id=sat_id,
            mesh=mesh,
            points_render=render_points,
            points_eci=trail_points_eci.copy(),
            color=actual_color,
        )

        # Add to scene based on color mode
        if self._color_mode == "altitude":
            altitudes = self._compute_altitudes(trail_points_eci)
            mesh.point_data["altitude"] = altitudes
            trail.actor = self._plotter.add_mesh(
                mesh,
                scalars="altitude",
                cmap="coolwarm",
                clim=[200, 36000],
                line_width=2,
                render_lines_as_tubes=True,
                show_scalar_bar=False,
                name=f"orbit_{sat_id}",
            )
        elif self._color_mode == "velocity":
            # Velocity coloring would need velocity data
            trail.actor = self._plotter.add_mesh(
                mesh,
                color=actual_color,
                line_width=2,
                render_lines_as_tubes=True,
                name=f"orbit_{sat_id}",
            )
        else:
            trail.actor = self._plotter.add_mesh(
                mesh,
                color=actual_color,
                line_width=2,
                render_lines_as_tubes=True,
                name=f"orbit_{sat_id}",
            )

        self._trails[sat_id] = trail

    def remove_orbit(self, sat_id: str) -> None:
        """Remove orbit trail for a satellite."""
        if sat_id in self._trails:
            trail = self._trails[sat_id]
            if trail.actor is not None:
                self._plotter.remove_actor(trail.actor)
            del self._trails[sat_id]

        if sat_id in self._ground_tracks:
            self._plotter.remove_actor(self._ground_tracks[sat_id])
            del self._ground_tracks[sat_id]

    def update_trail(self, sat_id: str, new_points_eci: np.ndarray) -> None:
        """Update trail points in-place."""
        if sat_id not in self._trails:
            return

        trail = self._trails[sat_id]
        render_points = new_points_eci / R_EARTH_EQUATORIAL

        if trail.mesh is not None and len(render_points) == len(trail.mesh.points):
            trail.mesh.points[:] = render_points
            trail.mesh.Modified()
        else:
            # Point count changed, recreate
            self.remove_orbit(sat_id)
            self.add_orbit(sat_id, new_points_eci, trail.color)

        trail.points_eci = new_points_eci.copy()
        trail.points_render = render_points

    def set_color_mode(self, mode: str) -> None:
        """Switch all trails between altitude/velocity/solid coloring."""
        self._color_mode = mode
        # Recreate all trails with new color mode
        trails_data = {
            sid: (t.points_eci, t.color)
            for sid, t in self._trails.items()
            if t.points_eci is not None
        }
        for sid in list(self._trails.keys()):
            self.remove_orbit(sid)
        for sid, (points, color) in trails_data.items():
            self.add_orbit(sid, points, color)

    def set_visibility(self, sat_id: str, visible: bool) -> None:
        """Show or hide a specific orbit trail."""
        if sat_id in self._trails:
            trail = self._trails[sat_id]
            trail.visible = visible
            if trail.actor is not None:
                trail.actor.SetVisibility(visible)

    def toggle_all(self, visible: bool) -> None:
        """Show or hide all orbit trails."""
        for trail in self._trails.values():
            trail.visible = visible
            if trail.actor is not None:
                trail.actor.SetVisibility(visible)

    def add_ground_track(
        self,
        sat_id: str,
        eci_points: np.ndarray,
        gmst_rad: float,
    ) -> None:
        """Project orbit onto Earth surface."""
        # Remove existing ground track
        if sat_id in self._ground_tracks:
            self._plotter.remove_actor(self._ground_tracks[sat_id])

        # Rotate ECI to ECEF
        cos_g = np.cos(gmst_rad)
        sin_g = np.sin(gmst_rad)
        ecef = np.empty_like(eci_points)
        ecef[:, 0] = eci_points[:, 0] * cos_g + eci_points[:, 1] * sin_g
        ecef[:, 1] = -eci_points[:, 0] * sin_g + eci_points[:, 1] * cos_g
        ecef[:, 2] = eci_points[:, 2]

        # Project to unit sphere surface (slightly above)
        norms = np.linalg.norm(ecef, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-10)
        surface_points = ecef / norms * (EARTH_RENDER_RADIUS + 0.003)

        # Convert to render coordinates
        surface_render = surface_points / R_EARTH_EQUATORIAL

        mesh = self._create_trail_mesh(surface_render)
        color = self._trails[sat_id].color if sat_id in self._trails else "#3B82F6"

        self._ground_tracks[sat_id] = self._plotter.add_mesh(
            mesh,
            color=color,
            line_width=1.5,
            opacity=0.5,
            name=f"ground_{sat_id}",
        )

    def remove_ground_track(self, sat_id: str) -> None:
        """Remove ground track for a satellite."""
        if sat_id in self._ground_tracks:
            self._plotter.remove_actor(self._ground_tracks[sat_id])
            del self._ground_tracks[sat_id]

    def _create_trail_mesh(self, points: np.ndarray) -> pv.PolyData:
        """Create a polyline mesh from ordered points."""
        n = len(points)
        if n < 2:
            return pv.PolyData(points)

        # Build polyline connectivity
        lines = np.empty(n + 1, dtype=np.int64)
        lines[0] = n
        lines[1:] = np.arange(n)

        return pv.PolyData(points.astype(np.float64), lines=lines)

    def _compute_altitudes(self, eci_points: np.ndarray) -> np.ndarray:
        """Compute altitude above Earth surface for each trail point (km)."""
        radii = np.linalg.norm(eci_points, axis=1)
        return radii - R_EARTH_EQUATORIAL

    @property
    def trails(self) -> dict[str, OrbitTrail]:
        return self._trails
