"""Main 3D scene manager.

Orchestrates all visualization components: Earth, orbits, satellites.
Manages camera, lighting, background, and the per-tick update cycle.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pyvista as pv

from core.coordinate_transforms import eci_to_render_coords
from core.propagator import OrbitalPropagator
from core.tle_parser import TLEData
from utils.constants import (
    EARTH_RENDER_RADIUS,
    R_EARTH_EQUATORIAL,
    SATELLITE_COLORS,
    SPACE_BACKGROUND,
)
from utils.time_utils import datetime_to_gmst, sun_position_eci
from visualization.earth_renderer import EarthRenderer
from visualization.orbit_renderer import OrbitRenderer
from visualization.satellite_renderer import SatelliteRenderer

logger = logging.getLogger(__name__)


class OrbitalScene:
    """Orchestrates all visualization components."""

    def __init__(self, plotter: pv.Plotter):
        self._plotter = plotter
        self.earth = EarthRenderer(plotter)
        self.orbits = OrbitRenderer(plotter)
        self.satellites = SatelliteRenderer(plotter)

        self._propagators: dict[str, OrbitalPropagator] = {}
        self._tle_data: dict[str, TLEData] = {}
        self._color_assignments: dict[str, str] = {}
        self._color_index: int = 0

        self._camera_mode: str = "free"
        self._follow_target: Optional[str] = None
        self._show_axes: bool = False
        self._show_grid: bool = False
        self._show_ground_tracks: bool = False
        self._show_terminator: bool = False
        self._axes_actor = None
        self._grid_actor = None
        self._starfield_actor = None

    def initialize(self, texture_path: Optional[Path] = None) -> None:
        """Set up scene: background, lighting, Earth, camera."""
        self._setup_background()
        self._setup_lighting()
        self.earth.initialize(texture_path)
        self._setup_camera()

    def add_satellite(self, tle_data: TLEData) -> Optional[str]:
        """Add a satellite to the scene.

        Returns sat_id on success, None on failure.
        """
        sat_id = str(tle_data.catalog_number)

        try:
            propagator = OrbitalPropagator(tle_data)
        except Exception as e:
            logger.error("Failed to create propagator for %s: %s", tle_data.name, e)
            return None

        self._propagators[sat_id] = propagator
        self._tle_data[sat_id] = tle_data

        # Assign color
        color = SATELLITE_COLORS[self._color_index % len(SATELLITE_COLORS)]
        self._color_assignments[sat_id] = color
        self._color_index += 1

        # Propagate current position
        now = datetime.now(timezone.utc)
        try:
            result = propagator.propagate(now)
            pos_render = eci_to_render_coords(result.position_eci)

            # Add marker
            self.satellites.add_satellite(sat_id, tle_data.name, pos_render, color)

            # Generate orbit trail (one full period)
            self._generate_orbit_trail(sat_id, propagator, now)

        except Exception as e:
            logger.error("Failed to propagate %s: %s", tle_data.name, e)
            # Still keep the satellite registered even if initial propagation fails
            return sat_id

        return sat_id

    def remove_satellite(self, sat_id: str) -> None:
        """Remove a satellite from the scene."""
        self.satellites.remove_satellite(sat_id)
        self.orbits.remove_orbit(sat_id)
        self.orbits.remove_ground_track(sat_id)
        self._propagators.pop(sat_id, None)
        self._tle_data.pop(sat_id, None)
        self._color_assignments.pop(sat_id, None)

    def update(self, sim_time: datetime) -> None:
        """Called each tick by SimulationController."""
        if sim_time.tzinfo is None:
            sim_time = sim_time.replace(tzinfo=timezone.utc)

        # Rotate Earth
        gmst = datetime_to_gmst(sim_time)
        self.earth.rotate_to_gmst(gmst)

        # Update satellite positions
        for sat_id, propagator in self._propagators.items():
            try:
                result = propagator.propagate(sim_time)
                self.satellites.update_position(
                    sat_id,
                    result.position_eci,
                    result.velocity_eci,
                )
            except Exception:
                pass  # Skip failed propagations silently during animation

        # Update terminator if enabled
        if self._show_terminator:
            sun_pos = sun_position_eci(sim_time)
            sun_render = sun_pos / np.linalg.norm(sun_pos)
            self.earth.set_terminator(sun_render, visible=True)

        # Update ground tracks if enabled
        if self._show_ground_tracks:
            for sat_id, propagator in self._propagators.items():
                if sat_id in self.orbits.trails:
                    trail = self.orbits.trails[sat_id]
                    if trail.points_eci is not None:
                        self.orbits.add_ground_track(sat_id, trail.points_eci, gmst)

        # Camera follow mode
        if self._camera_mode == "follow" and self._follow_target:
            self._update_follow_camera()

        # Render
        self._plotter.render()

    def get_satellite_data(self, sat_id: str, sim_time: datetime) -> Optional[dict]:
        """Get current orbital data for a satellite (for info panel)."""
        if sat_id not in self._propagators:
            return None

        if sim_time.tzinfo is None:
            sim_time = sim_time.replace(tzinfo=timezone.utc)

        propagator = self._propagators[sat_id]
        tle = self._tle_data[sat_id]

        try:
            result = propagator.propagate(sim_time)
            elements = propagator.get_orbital_elements(sim_time)

            return {
                "name": tle.name,
                "norad_id": tle.catalog_number,
                "lat": result.latitude,
                "lon": result.longitude,
                "alt": result.altitude,
                "vel": result.speed,
                "sma": elements.semi_major_axis,
                "ecc": elements.eccentricity,
                "inc": elements.inclination,
                "raan": elements.raan,
                "aop": elements.arg_perigee,
                "ta": elements.true_anomaly,
                "orbit_type": elements.orbit_type,
                "period": elements.period / 60.0,  # Convert to minutes
                "apogee": elements.apogee_altitude,
                "perigee": elements.perigee_altitude,
                "tle_age": tle.tle_age_days,
                "in_shadow": result.in_shadow,
            }
        except Exception as e:
            logger.error("Failed to get data for %s: %s", sat_id, e)
            return None

    def set_satellite_visible(self, sat_id: str, visible: bool) -> None:
        """Show or hide a satellite and its orbit."""
        self.satellites.set_visibility(sat_id, visible)
        self.orbits.set_visibility(sat_id, visible)

    def follow_satellite(self, sat_id: str) -> None:
        """Set camera to track a satellite."""
        self._camera_mode = "follow"
        self._follow_target = sat_id

    def free_camera(self) -> None:
        """Return to free orbit/pan/zoom camera."""
        self._camera_mode = "free"
        self._follow_target = None

    def focus_on_satellite(self, sat_id: str) -> None:
        """Move camera to look at a specific satellite."""
        if sat_id in self.satellites.satellites:
            vis = self.satellites.satellites[sat_id]
            if vis.current_pos is not None:
                pos = vis.current_pos
                direction = pos / max(np.linalg.norm(pos), 1e-10)
                cam_pos = pos + direction * 0.8
                self._plotter.camera.position = tuple(cam_pos)
                self._plotter.camera.focal_point = (0, 0, 0)

    def toggle_axes(self, visible: bool) -> None:
        """Toggle ECI reference axes."""
        self._show_axes = visible
        if visible and self._axes_actor is None:
            self._axes_actor = self._plotter.add_axes(
                line_width=2,
                color="white",
                xlabel="X",
                ylabel="Y",
                zlabel="Z",
            )
        elif not visible and self._axes_actor is not None:
            # Axes widget can't be easily removed, hide it
            self._show_axes = False

    def toggle_equatorial_grid(self, visible: bool) -> None:
        """Toggle equatorial plane grid."""
        self._show_grid = visible
        if visible and self._grid_actor is None:
            theta = np.linspace(0, 2 * np.pi, 360)
            r = 1.5
            points = np.column_stack([
                r * np.cos(theta),
                r * np.sin(theta),
                np.zeros(360),
            ])
            grid_mesh = pv.PolyData(points)
            lines = np.empty(361, dtype=np.int64)
            lines[0] = 360
            lines[1:] = np.arange(360)
            grid_mesh.lines = lines

            self._grid_actor = self._plotter.add_mesh(
                grid_mesh,
                color="#404040",
                line_width=1,
                opacity=0.3,
                name="eq_grid",
            )
        elif not visible and self._grid_actor is not None:
            self._plotter.remove_actor(self._grid_actor)
            self._grid_actor = None

    def toggle_ground_tracks(self, visible: bool) -> None:
        """Toggle ground track projection."""
        self._show_ground_tracks = visible
        if not visible:
            for sat_id in list(self.orbits._ground_tracks.keys()):
                self.orbits.remove_ground_track(sat_id)

    def toggle_terminator(self, visible: bool) -> None:
        """Toggle day/night terminator line."""
        self._show_terminator = visible
        if not visible:
            self.earth.set_terminator(np.array([1, 0, 0]), visible=False)

    def _generate_orbit_trail(
        self,
        sat_id: str,
        propagator: OrbitalPropagator,
        now: datetime,
    ) -> None:
        """Generate full orbit trail for a satellite."""
        from datetime import timedelta

        try:
            period_s = propagator.tle.orbital_period_seconds
            # Half period before and after current time
            start = now - timedelta(seconds=period_s / 2)
            end = now + timedelta(seconds=period_s / 2)
            step = max(1.0, period_s / 360)

            results = propagator.propagate_range(start, end, step)
            if results:
                positions = np.array([r.position_eci for r in results])
                color = self._color_assignments.get(sat_id, "#3B82F6")
                self.orbits.add_orbit(sat_id, positions, color)
        except Exception as e:
            logger.error("Failed to generate trail for %s: %s", sat_id, e)

    def _setup_background(self) -> None:
        """Dark space background with starfield."""
        self._plotter.set_background(SPACE_BACKGROUND)

        # Add random starfield
        n_stars = 2000
        phi = np.random.uniform(0, 2 * np.pi, n_stars)
        theta = np.arccos(np.random.uniform(-1, 1, n_stars))
        r = 50.0

        stars = np.column_stack([
            r * np.sin(theta) * np.cos(phi),
            r * np.sin(theta) * np.sin(phi),
            r * np.cos(theta),
        ])

        star_cloud = pv.PolyData(stars)
        brightness = np.random.power(3, n_stars)
        star_cloud.point_data["brightness"] = brightness

        self._starfield_actor = self._plotter.add_mesh(
            star_cloud,
            scalars="brightness",
            cmap="gray",
            point_size=2,
            render_points_as_spheres=True,
            show_scalar_bar=False,
            opacity=0.8,
            name="starfield",
        )

    def _setup_lighting(self) -> None:
        """Ambient + directional (sun) lighting."""
        self._plotter.remove_all_lights()

        sun_light = pv.Light(
            position=(10, 0, 0),
            focal_point=(0, 0, 0),
            color="#FFF5E0",
            intensity=0.9,
        )
        sun_light.positional = False
        self._plotter.add_light(sun_light)

        ambient = pv.Light(
            light_type="headlight",
            color="#B0C4DE",
            intensity=0.15,
        )
        self._plotter.add_light(ambient)

    def _setup_camera(self) -> None:
        """Initial camera position looking at Earth."""
        self._plotter.camera.position = (0, 0, 4.0)
        self._plotter.camera.focal_point = (0, 0, 0)
        self._plotter.camera.up = (0, 1, 0)
        self._plotter.camera.clipping_range = (0.01, 200)

    def _update_follow_camera(self) -> None:
        """Position camera behind the followed satellite."""
        if self._follow_target not in self.satellites.satellites:
            return

        vis = self.satellites.satellites[self._follow_target]
        if vis.current_pos is None:
            return

        pos = vis.current_pos
        pos_norm = np.linalg.norm(pos)
        if pos_norm < 1e-10:
            return

        direction = pos / pos_norm
        cam_pos = pos + direction * 0.5

        self._plotter.camera.position = tuple(cam_pos)
        self._plotter.camera.focal_point = (0, 0, 0)
        self._plotter.camera.up = (0, 0, 1)

    @property
    def plotter(self) -> pv.Plotter:
        return self._plotter

    @property
    def propagators(self) -> dict[str, OrbitalPropagator]:
        return self._propagators

    @property
    def satellite_ids(self) -> list[str]:
        return list(self._propagators.keys())
