"""Satellite marker rendering with labels, velocity vectors, and nadir lines.

Manages satellite markers as 3D spheres at their current propagated
positions, with toggle-able labels, velocity arrows, and nadir lines.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pyvista as pv

from utils.constants import (
    EARTH_RENDER_RADIUS,
    R_EARTH_EQUATORIAL,
    SATELLITE_COLORS,
    SATELLITE_HIGHLIGHT_RADIUS,
    SATELLITE_MARKER_RADIUS,
    VELOCITY_VECTOR_SCALE,
)

logger = logging.getLogger(__name__)


@dataclass
class SatelliteVisual:
    """Holds all VTK actors for one satellite."""

    sat_id: str
    name: str
    color: str
    marker_mesh: Optional[pv.PolyData] = None
    marker_actor: object = None
    label_actor: object = None
    velocity_actor: object = None
    nadir_actor: object = None
    is_selected: bool = False
    is_visible: bool = True
    current_pos: Optional[np.ndarray] = None


class SatelliteRenderer:
    """Manages satellite markers, labels, velocity vectors, and nadir lines."""

    def __init__(self, plotter: pv.Plotter):
        self._plotter = plotter
        self._satellites: dict[str, SatelliteVisual] = {}
        self._selected_id: Optional[str] = None
        self._show_labels: bool = True
        self._show_velocity: bool = False
        self._show_nadir: bool = False

    def add_satellite(
        self,
        sat_id: str,
        name: str,
        position_render: np.ndarray,
        color: str = "#3B82F6",
    ) -> None:
        """Create marker sphere at initial position."""
        if sat_id in self._satellites:
            self.remove_satellite(sat_id)

        marker = pv.Sphere(
            radius=SATELLITE_MARKER_RADIUS,
            center=position_render,
            theta_resolution=12,
            phi_resolution=12,
        )

        actor = self._plotter.add_mesh(
            marker,
            color=color,
            smooth_shading=True,
            name=f"sat_{sat_id}",
        )

        vis = SatelliteVisual(
            sat_id=sat_id,
            name=name,
            color=color,
            marker_mesh=marker,
            marker_actor=actor,
            current_pos=position_render.copy(),
        )

        # Add label if enabled
        if self._show_labels:
            self._add_label(vis)

        self._satellites[sat_id] = vis

    def remove_satellite(self, sat_id: str) -> None:
        """Remove all actors for a satellite."""
        if sat_id not in self._satellites:
            return

        vis = self._satellites[sat_id]
        for actor in [vis.marker_actor, vis.label_actor, vis.velocity_actor, vis.nadir_actor]:
            if actor is not None:
                self._plotter.remove_actor(actor)

        del self._satellites[sat_id]

        if self._selected_id == sat_id:
            self._selected_id = None

    def update_position(
        self,
        sat_id: str,
        position_eci: np.ndarray,
        velocity_eci: Optional[np.ndarray] = None,
    ) -> None:
        """Move satellite marker to new position. Called each tick."""
        if sat_id not in self._satellites:
            return

        vis = self._satellites[sat_id]
        pos_render = position_eci / R_EARTH_EQUATORIAL

        if vis.marker_mesh is not None and vis.current_pos is not None:
            delta = pos_render - vis.current_pos
            vis.marker_mesh.translate(delta, inplace=True)

        vis.current_pos = pos_render.copy()

        # Update label position
        if vis.label_actor is not None:
            self._plotter.remove_actor(vis.label_actor)
            if self._show_labels and vis.is_visible:
                self._add_label(vis)

        # Update velocity vector
        if self._show_velocity and velocity_eci is not None and vis.is_visible:
            self._update_velocity_arrow(vis, pos_render, velocity_eci)

        # Update nadir line
        if self._show_nadir and vis.is_visible:
            self._update_nadir_line(vis, pos_render)

    def select(self, sat_id: str) -> None:
        """Highlight selected satellite, deselect previous."""
        # Deselect previous
        if self._selected_id and self._selected_id in self._satellites:
            prev = self._satellites[self._selected_id]
            prev.is_selected = False
            if prev.marker_actor is not None:
                prop = prev.marker_actor.GetProperty()
                rgb = self._hex_to_rgb(prev.color)
                prop.SetColor(rgb[0], rgb[1], rgb[2])

        # Select new
        self._selected_id = sat_id
        if sat_id in self._satellites:
            vis = self._satellites[sat_id]
            vis.is_selected = True
            if vis.marker_actor is not None:
                prop = vis.marker_actor.GetProperty()
                prop.SetColor(1.0, 1.0, 1.0)  # White highlight

    def deselect(self) -> None:
        """Deselect current satellite."""
        if self._selected_id and self._selected_id in self._satellites:
            vis = self._satellites[self._selected_id]
            vis.is_selected = False
            if vis.marker_actor is not None:
                rgb = self._hex_to_rgb(vis.color)
                vis.marker_actor.GetProperty().SetColor(rgb[0], rgb[1], rgb[2])
        self._selected_id = None

    def set_visibility(self, sat_id: str, visible: bool) -> None:
        """Show or hide a specific satellite."""
        if sat_id not in self._satellites:
            return
        vis = self._satellites[sat_id]
        vis.is_visible = visible
        if vis.marker_actor:
            vis.marker_actor.SetVisibility(visible)
        if vis.label_actor:
            vis.label_actor.SetVisibility(visible)
        if vis.velocity_actor:
            vis.velocity_actor.SetVisibility(visible)
        if vis.nadir_actor:
            vis.nadir_actor.SetVisibility(visible)

    def toggle_labels(self, visible: bool) -> None:
        """Toggle labels for all satellites."""
        self._show_labels = visible
        for vis in self._satellites.values():
            if visible and vis.is_visible:
                if vis.label_actor is None:
                    self._add_label(vis)
                else:
                    vis.label_actor.SetVisibility(True)
            elif vis.label_actor is not None:
                vis.label_actor.SetVisibility(False)

    def toggle_velocity_vectors(self, visible: bool) -> None:
        """Toggle velocity vectors for all satellites."""
        self._show_velocity = visible
        if not visible:
            for vis in self._satellites.values():
                if vis.velocity_actor is not None:
                    self._plotter.remove_actor(vis.velocity_actor)
                    vis.velocity_actor = None

    def toggle_nadir_lines(self, visible: bool) -> None:
        """Toggle nadir lines for all satellites."""
        self._show_nadir = visible
        if not visible:
            for vis in self._satellites.values():
                if vis.nadir_actor is not None:
                    self._plotter.remove_actor(vis.nadir_actor)
                    vis.nadir_actor = None

    def _add_label(self, vis: SatelliteVisual) -> None:
        """Add a text label above the satellite."""
        if vis.current_pos is None:
            return

        label_pos = vis.current_pos + np.array([0, 0, SATELLITE_MARKER_RADIUS * 2])
        point = pv.PolyData(label_pos.reshape(1, 3))
        point["labels"] = [vis.name]

        vis.label_actor = self._plotter.add_point_labels(
            point,
            "labels",
            font_size=10,
            point_size=0,
            text_color="white",
            font_family="courier",
            show_points=False,
            always_visible=True,
            name=f"label_{vis.sat_id}",
        )

    def _update_velocity_arrow(
        self,
        vis: SatelliteVisual,
        pos_render: np.ndarray,
        velocity_eci: np.ndarray,
    ) -> None:
        """Update or create velocity vector arrow."""
        if vis.velocity_actor is not None:
            self._plotter.remove_actor(vis.velocity_actor)

        vel_render = velocity_eci / R_EARTH_EQUATORIAL * VELOCITY_VECTOR_SCALE * 50
        vel_mag = np.linalg.norm(vel_render)
        if vel_mag < 1e-10:
            return

        direction = vel_render / vel_mag
        arrow = pv.Arrow(
            start=pos_render,
            direction=direction,
            scale=vel_mag,
            tip_length=0.2,
            tip_radius=0.05,
            shaft_radius=0.02,
        )

        vis.velocity_actor = self._plotter.add_mesh(
            arrow,
            color="#F59E0B",
            name=f"vel_{vis.sat_id}",
        )

    def _update_nadir_line(
        self, vis: SatelliteVisual, pos_render: np.ndarray
    ) -> None:
        """Update nadir line from satellite to Earth surface."""
        if vis.nadir_actor is not None:
            self._plotter.remove_actor(vis.nadir_actor)

        pos_norm = np.linalg.norm(pos_render)
        if pos_norm < 1e-10:
            return

        surface_point = pos_render / pos_norm * EARTH_RENDER_RADIUS

        line_points = np.array([pos_render, surface_point])
        line = pv.Line(pos_render, surface_point)

        vis.nadir_actor = self._plotter.add_mesh(
            line,
            color="#A3A3A3",
            line_width=1,
            opacity=0.5,
            name=f"nadir_{vis.sat_id}",
        )

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
        """Convert hex color to normalized RGB tuple."""
        h = hex_color.lstrip("#")
        return (
            int(h[0:2], 16) / 255.0,
            int(h[2:4], 16) / 255.0,
            int(h[4:6], 16) / 255.0,
        )

    @property
    def satellites(self) -> dict[str, SatelliteVisual]:
        return self._satellites

    @property
    def selected_id(self) -> Optional[str]:
        return self._selected_id
