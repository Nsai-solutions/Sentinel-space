"""Earth sphere rendering with texture mapping and rotation.

Creates a UV-mapped sphere with NASA Blue Marble texture,
handles rotation to match GMST, and optional day/night terminator.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pyvista as pv

from utils.constants import (
    EARTH_RENDER_RADIUS,
    NASA_BLUE_MARBLE_URL,
    R_EARTH_EQUATORIAL,
    RAD_TO_DEG,
)

logger = logging.getLogger(__name__)


class EarthRenderer:
    """Manages Earth sphere mesh, texture, rotation, and terminator."""

    TEXTURE_CACHE_DIR = Path.home() / ".orbital_propagator" / "textures"
    TEXTURE_FILENAME = "earth_texture.jpg"

    def __init__(self, plotter: pv.Plotter):
        self._plotter = plotter
        self._earth_mesh: Optional[pv.PolyData] = None
        self._earth_actor = None
        self._terminator_actor = None
        self._current_rotation_deg: float = 0.0

    def initialize(self, texture_path: Optional[Path] = None) -> None:
        """Create Earth sphere and apply texture."""
        self._earth_mesh = self._create_earth_mesh()

        # Try to load texture
        tex = self._load_texture(texture_path)

        if tex is not None:
            self._earth_actor = self._plotter.add_mesh(
                self._earth_mesh,
                texture=tex,
                smooth_shading=True,
                name="earth",
            )
        else:
            # Fallback: solid colored sphere
            self._earth_actor = self._plotter.add_mesh(
                self._earth_mesh,
                color="#1E3A5F",
                smooth_shading=True,
                name="earth",
            )

    def _create_earth_mesh(self) -> pv.PolyData:
        """Create a UV-mapped sphere for equirectangular texture."""
        sphere = pv.Sphere(
            radius=EARTH_RENDER_RADIUS,
            theta_resolution=100,
            phi_resolution=100,
        )

        # Manual UV mapping for equirectangular projection
        points = sphere.points
        tex_coords = np.zeros((sphere.n_points, 2))

        for i in range(sphere.n_points):
            x, y, z = points[i]
            # Longitude: atan2(y, x) mapped to [0, 1]
            lon = np.arctan2(y, x)
            tex_coords[i, 0] = 0.5 + lon / (2.0 * np.pi)
            # Latitude: asin(z/r) mapped to [0, 1]
            r = np.sqrt(x * x + y * y + z * z)
            if r > 0:
                tex_coords[i, 1] = 0.5 + np.arcsin(np.clip(z / r, -1, 1)) / np.pi

        sphere.active_texture_coordinates = tex_coords
        return sphere

    def _load_texture(self, texture_path: Optional[Path] = None) -> Optional[pv.Texture]:
        """Load texture from cache or provided path."""
        # Check provided path first
        if texture_path and texture_path.exists():
            try:
                return pv.Texture(str(texture_path))
            except Exception as e:
                logger.warning("Failed to load texture from %s: %s", texture_path, e)

        # Check default cache location
        cache_path = self.TEXTURE_CACHE_DIR / self.TEXTURE_FILENAME
        if cache_path.exists():
            try:
                return pv.Texture(str(cache_path))
            except Exception as e:
                logger.warning("Failed to load cached texture: %s", e)

        # Check project data directory
        data_path = Path(__file__).parent.parent / "data" / "textures" / self.TEXTURE_FILENAME
        if data_path.exists():
            try:
                return pv.Texture(str(data_path))
            except Exception as e:
                logger.warning("Failed to load data texture: %s", e)

        logger.info("No Earth texture found, using solid color fallback")
        return self._create_procedural_texture()

    def _create_procedural_texture(self) -> Optional[pv.Texture]:
        """Generate a simple blue sphere texture as fallback."""
        try:
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (512, 256), color=(20, 60, 140))
            draw = ImageDraw.Draw(img)

            # Add some simple "continent" shapes as lighter patches
            patches = [
                (120, 60, 180, 120),   # Europe/Africa-ish
                (200, 80, 260, 130),   # Asia-ish
                (350, 70, 420, 130),   # Americas-ish
                (80, 140, 140, 180),   # South
            ]
            for x1, y1, x2, y2 in patches:
                draw.ellipse([x1, y1, x2, y2], fill=(30, 100, 60))

            arr = np.array(img)
            return pv.Texture(arr)
        except ImportError:
            logger.warning("Pillow not available for procedural texture")
            return None

    def rotate_to_gmst(self, gmst_rad: float) -> None:
        """Rotate Earth mesh to match Greenwich Mean Sidereal Time."""
        if self._earth_actor is None:
            return

        degrees = gmst_rad * RAD_TO_DEG
        # Reset orientation and apply new rotation
        self._earth_actor.SetOrientation(0, 0, 0)
        self._earth_actor.RotateZ(degrees)
        self._current_rotation_deg = degrees

    def set_terminator(
        self, sun_direction: np.ndarray, visible: bool = True
    ) -> None:
        """Show/hide day-night terminator line on Earth's surface."""
        if not visible:
            if self._terminator_actor is not None:
                self._plotter.remove_actor(self._terminator_actor)
                self._terminator_actor = None
            return

        points = self._compute_terminator_points(sun_direction)
        if points is not None:
            if self._terminator_actor is not None:
                self._plotter.remove_actor(self._terminator_actor)

            line = pv.Spline(points, n_points=180)
            self._terminator_actor = self._plotter.add_mesh(
                line,
                color="#F59E0B",
                line_width=2,
                name="terminator",
            )

    def _compute_terminator_points(
        self, sun_dir: np.ndarray, n_points: int = 180
    ) -> Optional[np.ndarray]:
        """Compute points along the terminator circle on Earth surface."""
        sun_norm = np.linalg.norm(sun_dir)
        if sun_norm < 1e-10:
            return None

        sun_unit = sun_dir / sun_norm

        # Find two perpendicular vectors
        if abs(sun_unit[2]) < 0.9:
            perp1 = np.cross(sun_unit, np.array([0.0, 0.0, 1.0]))
        else:
            perp1 = np.cross(sun_unit, np.array([1.0, 0.0, 0.0]))

        perp1 /= np.linalg.norm(perp1)
        perp2 = np.cross(sun_unit, perp1)

        angles = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
        r = EARTH_RENDER_RADIUS * 1.001  # Slightly above surface

        points = np.empty((n_points, 3))
        for i, a in enumerate(angles):
            points[i] = r * (np.cos(a) * perp1 + np.sin(a) * perp2)

        return points

    @property
    def mesh(self) -> Optional[pv.PolyData]:
        return self._earth_mesh

    @property
    def actor(self):
        return self._earth_actor
