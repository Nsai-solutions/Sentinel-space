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

    # Screening configuration
    screening_window_days = Column(Float, nullable=True, default=7.0)
    screening_threshold_km = Column(Float, nullable=True, default=25.0)
    auto_screen = Column(Boolean, default=True)

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


class ConjunctionHistory(Base):
    """Snapshot of each conjunction at each screening run.

    While ConjunctionEvent stores the current/latest state, this table
    accumulates all observations so operators can see trends over time.
    """
    __tablename__ = "conjunction_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    primary_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    secondary_norad_id = Column(Integer, nullable=False, index=True)
    secondary_name = Column(String(128), nullable=True)

    # Snapshot of conjunction state at this screening
    tca = Column(DateTime, nullable=False)
    miss_distance_m = Column(Float, nullable=False)
    radial_m = Column(Float, nullable=True)
    in_track_m = Column(Float, nullable=True)
    cross_track_m = Column(Float, nullable=True)
    relative_velocity_kms = Column(Float, nullable=True)
    collision_probability = Column(Float, nullable=True)
    threat_level = Column(Enum(ThreatLevel), nullable=True)

    # Metadata
    screening_job_id = Column(Integer, ForeignKey("screening_jobs.id"), nullable=True)
    screened_at = Column(DateTime, server_default=func.now())


class NotificationPreferences(Base):
    """Global email notification preferences (single row, no user auth yet)."""
    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=True)
    email_enabled = Column(Boolean, default=False)

    notify_critical = Column(Boolean, default=True)
    notify_high = Column(Boolean, default=True)
    notify_moderate = Column(Boolean, default=False)
    notify_low = Column(Boolean, default=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class APIKey(Base):
    """API key for programmatic access."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    key_prefix = Column(String(8), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    last_used_at = Column(DateTime, nullable=True)


class AlertConfig(Base):
    __tablename__ = "alert_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)
    critical_threshold = Column(Float, default=1e-3)
    high_threshold = Column(Float, default=1e-4)
    moderate_threshold = Column(Float, default=1e-5)
    min_distance_km = Column(Float, nullable=True)
    enabled = Column(Boolean, default=True)
