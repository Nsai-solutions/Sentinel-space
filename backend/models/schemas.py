"""Pydantic schemas for API request/response validation."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---


class ThreatLevel(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    NONE = "NONE"


class EventStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# --- Assets ---


class AssetCreate(BaseModel):
    norad_id: Optional[int] = None
    name: Optional[str] = None
    tle_line1: Optional[str] = None
    tle_line2: Optional[str] = None
    mass_kg: Optional[float] = None
    cross_section_m2: Optional[float] = None
    hard_body_radius_m: float = 1.0
    maneuverable: bool = False
    delta_v_budget_ms: Optional[float] = None


class AssetProperties(BaseModel):
    mass_kg: Optional[float] = None
    cross_section_m2: Optional[float] = None
    hard_body_radius_m: Optional[float] = None
    maneuverable: Optional[bool] = None
    delta_v_budget_ms: Optional[float] = None


class AssetResponse(BaseModel):
    id: int
    norad_id: int
    name: str
    orbit_type: Optional[str] = None
    tle_epoch: Optional[datetime] = None
    mass_kg: Optional[float] = None
    cross_section_m2: Optional[float] = None
    maneuverable: bool = False
    threat_summary: dict = Field(default_factory=dict)
    active_conjunctions: int = 0

    model_config = {"from_attributes": True}


class AssetDetail(AssetResponse):
    tle_line1: str
    tle_line2: str
    hard_body_radius_m: Optional[float] = None
    delta_v_budget_ms: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_km: Optional[float] = None
    velocity_kms: Optional[float] = None
    orbital_elements: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --- Conjunctions ---


class ConjunctionResponse(BaseModel):
    id: int
    primary_asset_name: str
    primary_norad_id: int
    secondary_name: Optional[str] = None
    secondary_norad_id: int
    secondary_object_type: Optional[str] = None
    tca: datetime
    time_to_tca_hours: Optional[float] = None
    miss_distance_m: float
    relative_velocity_kms: Optional[float] = None
    collision_probability: Optional[float] = None
    threat_level: ThreatLevel = ThreatLevel.NONE
    status: EventStatus = EventStatus.ACTIVE

    model_config = {"from_attributes": True}


class ConjunctionDetail(ConjunctionResponse):
    radial_m: Optional[float] = None
    in_track_m: Optional[float] = None
    cross_track_m: Optional[float] = None
    max_collision_probability: Optional[float] = None
    combined_hard_body_radius_m: Optional[float] = None
    primary_sigma_radial_m: Optional[float] = None
    primary_sigma_in_track_m: Optional[float] = None
    primary_sigma_cross_track_m: Optional[float] = None
    secondary_sigma_radial_m: Optional[float] = None
    secondary_sigma_in_track_m: Optional[float] = None
    secondary_sigma_cross_track_m: Optional[float] = None
    maneuver_options: list[ManeuverOptionResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --- Screening ---


class ScreeningRequest(BaseModel):
    asset_ids: list[int] = Field(default_factory=list)
    time_window_days: float = 7.0
    distance_threshold_km: float = 5.0


class ScreeningStatusResponse(BaseModel):
    job_id: int
    status: JobStatus
    progress: float = 0.0
    total_objects: int = 0
    candidates_found: int = 0
    conjunctions_found: int = 0
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


# --- Maneuvers ---


class ManeuverRequest(BaseModel):
    conjunction_id: int
    pc_threshold: float = 1e-5


class ManeuverOptionResponse(BaseModel):
    id: int
    label: str
    direction: str
    delta_v_ms: float
    timing_before_tca_orbits: float
    new_miss_distance_m: Optional[float] = None
    new_collision_probability: Optional[float] = None
    fuel_cost_pct: Optional[float] = None
    secondary_conjunctions_count: int = 0

    model_config = {"from_attributes": True}


class SecondaryCheckRequest(BaseModel):
    maneuver_id: int


# --- Alerts ---


class AlertResponse(BaseModel):
    id: int
    asset_id: Optional[int] = None
    conjunction_id: Optional[int] = None
    threat_level: ThreatLevel
    message: str
    reason: Optional[str] = None
    status: str = "NEW"
    created_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AlertConfigRequest(BaseModel):
    asset_id: Optional[int] = None
    critical_threshold: float = 1e-3
    high_threshold: float = 1e-4
    moderate_threshold: float = 1e-5
    min_distance_km: Optional[float] = None
    enabled: bool = True


# --- Orbit / Propagation ---


class PropagationPoint(BaseModel):
    datetime_utc: str
    latitude: float
    longitude: float
    altitude_km: float
    velocity_kms: float
    in_shadow: bool = False
    position_eci: list[float] = Field(default_factory=list)
    velocity_eci: list[float] = Field(default_factory=list)


class OrbitalElementsResponse(BaseModel):
    semi_major_axis_km: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float
    arg_perigee_deg: float
    true_anomaly_deg: float
    period_min: float
    apogee_alt_km: float
    perigee_alt_km: float
    orbit_type: str
    specific_energy: float
    angular_momentum: float


class GroundTrackResponse(BaseModel):
    points: list[dict]


# --- Environment ---


class CatalogStatsResponse(BaseModel):
    total_objects: int
    payloads: int
    rocket_bodies: int
    debris: int
    unknown: int


class DensityBin(BaseModel):
    altitude_min_km: float
    altitude_max_km: float
    object_count: int
    density: float


# --- Reports ---


class ReportRequest(BaseModel):
    asset_ids: list[int] = Field(default_factory=list)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    report_type: str = "conjunction_summary"


# --- TLE ---


class TLEUpload(BaseModel):
    tle_text: str


class TLEResponse(BaseModel):
    norad_id: int
    name: str
    line1: str
    line2: str
    epoch: Optional[str] = None
    inclination: Optional[float] = None
    orbit_type: Optional[str] = None
