"""Physical constants for orbital mechanics calculations.

All values use km, kg, seconds as base units unless otherwise noted.
WGS84 ellipsoid parameters are used for Earth shape modeling.
"""

import math

# --- Earth Gravitational Parameters ---
MU_EARTH: float = 398600.4418  # km^3/s^2

# --- Earth Shape (WGS84) ---
R_EARTH: float = 6371.0  # km -- mean radius
R_EARTH_EQUATORIAL: float = 6378.137  # km -- semi-major axis
R_EARTH_POLAR: float = 6356.752  # km -- semi-minor axis
FLATTENING: float = 1.0 / 298.257223563
ECCENTRICITY_SQ: float = FLATTENING * (2.0 - FLATTENING)

# --- Perturbation ---
J2: float = 1.08263e-3

# --- Earth Rotation ---
EARTH_ROTATION_RATE: float = 7.2921159e-5  # rad/s
SECONDS_PER_DAY: float = 86400.0
SECONDS_PER_SIDEREAL_DAY: float = 86164.0905

# --- Axial Tilt ---
EARTH_AXIAL_TILT: float = 23.44  # degrees

# --- Light ---
SPEED_OF_LIGHT: float = 299792.458  # km/s

# --- Sun Parameters (for shadow calculations) ---
SUN_RADIUS: float = 695700.0  # km
AU_KM: float = 149597870.7  # km -- 1 Astronomical Unit

# --- Derived Math Constants ---
TWO_PI: float = 2.0 * math.pi
DEG_TO_RAD: float = math.pi / 180.0
RAD_TO_DEG: float = 180.0 / math.pi

# --- Orbit Classification Thresholds ---
LEO_MAX_ALT: float = 2000.0  # km
GEO_ALT: float = 35786.0  # km
SIDEREAL_DAY_SECONDS: float = 86164.0905

# --- Celestrak API ---
CELESTRAK_BASE_URL: str = "https://celestrak.org/NORAD/elements/gp.php"
NASA_BLUE_MARBLE_URL: str = (
    "https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/"
    "world.topo.bathy.200412.3x5400x2700.jpg"
)

# --- Curated Satellite Groups ---
CELESTRAK_GROUPS: dict[str, str] = {
    "ISS & Crew Dragon": "stations",
    "GPS Constellation": "gps-ops",
    "Starlink": "starlink",
    "Weather Satellites": "weather",
    "Science & Hubble": "science",
    "Geostationary": "geo",
}

# --- Visualization Constants ---
EARTH_RENDER_RADIUS: float = 1.0
SATELLITE_MARKER_RADIUS: float = 0.015
SATELLITE_HIGHLIGHT_RADIUS: float = 0.025
VELOCITY_VECTOR_SCALE: float = 0.1

# --- UI Color Palette ---
ACCENT_COLOR: str = "#2563EB"
ACCENT_HOVER: str = "#1D4ED8"
BG_PRIMARY: str = "#FFFFFF"
BG_SECONDARY: str = "#FAFAFA"
BG_TERTIARY: str = "#F5F5F5"
TEXT_PRIMARY: str = "#171717"
TEXT_SECONDARY: str = "#525252"
TEXT_TERTIARY: str = "#A3A3A3"
BORDER_LIGHT: str = "#E5E5E5"
BORDER_MEDIUM: str = "#D4D4D4"
SPACE_BACKGROUND: str = "#0A0A0F"
STATUS_SUCCESS: str = "#16A34A"
STATUS_WARNING: str = "#D97706"
STATUS_ERROR: str = "#DC2626"
STATUS_INFO: str = "#0EA5E9"

# --- Orbit Trail Colors ---
ORBIT_COLOR_LEO: str = "#3B82F6"
ORBIT_COLOR_MEO: str = "#10B981"
ORBIT_COLOR_GEO: str = "#EF4444"
ORBIT_COLOR_HEO: str = "#F59E0B"

# --- Default Satellite Colors (for solid-color mode) ---
SATELLITE_COLORS: list[str] = [
    "#3B82F6",  # Blue
    "#EF4444",  # Red
    "#10B981",  # Green
    "#F59E0B",  # Amber
    "#8B5CF6",  # Purple
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#F97316",  # Orange
    "#14B8A6",  # Teal
    "#6366F1",  # Indigo
]
