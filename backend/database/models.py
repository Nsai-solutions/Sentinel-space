"""SQLAlchemy ORM models for SentinelSpace."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Boolean,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


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


class AlertStatus(str, enum.Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ACTION_TAKEN = "ACTION_TAKEN"
    RESOLVED = "RESOLVED"


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    norad_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    tle_line1 = Column(String(70), nullable=False)
    tle_line2 = Column(String(70), nullable=False)
    tle_epoch = Column(DateTime, nullable=True)

    # Physical properties
    mass_kg = Column(Float, nullable=True)
    cross_section_m2 = Column(Float, nullable=True)
    hard_body_radius_m = Column(Float, nullable=True, default=1.0)
    maneuverable = Column(Boolean, default=False)
    delta_v_budget_ms = Column(Float, nullable=True)

    # Metadata
    orbit_type = Column(String(16), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    conjunctions = relationship(
        "ConjunctionEvent", back_populates="primary_asset", cascade="all, delete-orphan"
    )
    alerts = relationship("Alert", back_populates="asset", cascade="all, delete-orphan")


class ConjunctionEvent(Base):
    __tablename__ = "conjunction_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    primary_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    secondary_norad_id = Column(Integer, nullable=False, index=True)
    secondary_name = Column(String(128), nullable=True)
    secondary_object_type = Column(String(32), nullable=True)

    # Conjunction geometry
    tca = Column(DateTime, nullable=False, index=True)
    miss_distance_m = Column(Float, nullable=False)
    radial_m = Column(Float, nullable=True)
    in_track_m = Column(Float, nullable=True)
    cross_track_m = Column(Float, nullable=True)
    relative_velocity_kms = Column(Float, nullable=True)

    # Risk assessment
    collision_probability = Column(Float, nullable=True)
    max_collision_probability = Column(Float, nullable=True)
    threat_level = Column(Enum(ThreatLevel), default=ThreatLevel.NONE, index=True)
    combined_hard_body_radius_m = Column(Float, nullable=True)

    # Uncertainty
    primary_sigma_radial_m = Column(Float, nullable=True)
    primary_sigma_in_track_m = Column(Float, nullable=True)
    primary_sigma_cross_track_m = Column(Float, nullable=True)
    secondary_sigma_radial_m = Column(Float, nullable=True)
    secondary_sigma_in_track_m = Column(Float, nullable=True)
    secondary_sigma_cross_track_m = Column(Float, nullable=True)

    # Status
    status = Column(Enum(EventStatus), default=EventStatus.ACTIVE)
    screening_job_id = Column(Integer, ForeignKey("screening_jobs.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    primary_asset = relationship("Asset", back_populates="conjunctions")
    maneuver_options = relationship(
        "ManeuverOption", back_populates="conjunction", cascade="all, delete-orphan"
    )


class ScreeningJob(Base):
    __tablename__ = "screening_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING)
    progress = Column(Float, default=0.0)
    total_objects = Column(Integer, default=0)
    candidates_found = Column(Integer, default=0)
    conjunctions_found = Column(Integer, default=0)

    # Config
    time_window_days = Column(Float, default=7.0)
    distance_threshold_km = Column(Float, default=5.0)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


class ManeuverOption(Base):
    __tablename__ = "maneuver_options"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conjunction_id = Column(Integer, ForeignKey("conjunction_events.id"), nullable=False)
    label = Column(String(8), nullable=False)
    direction = Column(String(16), nullable=False)
    delta_v_ms = Column(Float, nullable=False)
    timing_before_tca_orbits = Column(Float, nullable=False)
    new_miss_distance_m = Column(Float, nullable=True)
    new_collision_probability = Column(Float, nullable=True)
    fuel_cost_pct = Column(Float, nullable=True)

    # Secondary conjunction check
    secondary_conjunctions_count = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())

    conjunction = relationship("ConjunctionEvent", back_populates="maneuver_options")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    conjunction_id = Column(Integer, ForeignKey("conjunction_events.id"), nullable=True)
    threat_level = Column(Enum(ThreatLevel), nullable=False)
    message = Column(Text, nullable=False)
    reason = Column(String(64), nullable=True)

    status = Column(Enum(AlertStatus), default=AlertStatus.NEW)
    created_at = Column(DateTime, server_default=func.now())
    acknowledged_at = Column(DateTime, nullable=True)

    asset = relationship("Asset", back_populates="alerts")


class AlertConfig(Base):
    __tablename__ = "alert_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    critical_threshold = Column(Float, default=1e-3)
    high_threshold = Column(Float, default=1e-4)
    moderate_threshold = Column(Float, default=1e-5)
    min_distance_km = Column(Float, nullable=True)
    enabled = Column(Boolean, default=True)
