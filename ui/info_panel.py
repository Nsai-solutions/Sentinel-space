"""Satellite info panel displaying orbital data for the selected satellite."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class InfoPanelWidget(QGroupBox):
    """Displays detailed orbital data for the selected satellite."""

    def __init__(self, parent=None):
        super().__init__("SATELLITE INFO", parent)

        layout = QVBoxLayout()
        layout.setSpacing(4)

        # Name + NORAD ID header
        self.name_label = QLabel("No satellite selected")
        self.name_label.setObjectName("titleLabel")
        layout.addWidget(self.name_label)

        self.norad_label = QLabel("")
        self.norad_label.setObjectName("subtitleLabel")
        layout.addWidget(self.norad_label)

        self.shadow_label = QLabel("")
        self.shadow_label.setObjectName("unitLabel")
        layout.addWidget(self.shadow_label)

        layout.addSpacing(8)

        # Data rows
        self.data_layout = QFormLayout()
        self.data_layout.setSpacing(4)
        self.data_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.data_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )

        self._fields: dict[str, QLabel] = {}

        field_defs = [
            ("lat", "Latitude", "deg"),
            ("lon", "Longitude", "deg"),
            ("alt", "Altitude", "km"),
            ("vel", "Velocity", "km/s"),
            ("sma", "Semi-major Axis", "km"),
            ("ecc", "Eccentricity", ""),
            ("inc", "Inclination", "deg"),
            ("raan", "RAAN", "deg"),
            ("aop", "Arg. Perigee", "deg"),
            ("ta", "True Anomaly", "deg"),
            ("orbit_type", "Orbit Type", ""),
            ("period", "Period", "min"),
            ("apogee", "Apogee Alt", "km"),
            ("perigee", "Perigee Alt", "km"),
            ("tle_age", "TLE Age", "days"),
        ]

        for key, label, unit in field_defs:
            value_label = QLabel("--")
            value_label.setObjectName("valueLabel")

            if unit:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(4)
                row_layout.addWidget(value_label, stretch=1)
                unit_lbl = QLabel(unit)
                unit_lbl.setObjectName("unitLabel")
                unit_lbl.setFixedWidth(40)
                row_layout.addWidget(unit_lbl)
                self.data_layout.addRow(label + ":", row_widget)
            else:
                self.data_layout.addRow(label + ":", value_label)

            self._fields[key] = value_label

        layout.addLayout(self.data_layout)
        self.setLayout(layout)

    def update_data(self, data: dict) -> None:
        """Update all fields with new satellite data."""
        self.name_label.setText(data.get("name", "Unknown"))
        norad_id = data.get("norad_id", "N/A")
        self.norad_label.setText(f"NORAD ID: {norad_id}")

        in_shadow = data.get("in_shadow", False)
        self.shadow_label.setText("In Earth's shadow" if in_shadow else "In sunlight")

        formatters = {
            "lat": lambda v: f"{v:+.4f}",
            "lon": lambda v: f"{v:+.4f}",
            "alt": lambda v: f"{v:,.1f}",
            "vel": lambda v: f"{v:.3f}",
            "sma": lambda v: f"{v:,.1f}",
            "ecc": lambda v: f"{v:.6f}",
            "inc": lambda v: f"{v:.4f}",
            "raan": lambda v: f"{v:.4f}",
            "aop": lambda v: f"{v:.4f}",
            "ta": lambda v: f"{v:.4f}",
            "period": lambda v: f"{v:.2f}",
            "apogee": lambda v: f"{v:,.1f}",
            "perigee": lambda v: f"{v:,.1f}",
            "tle_age": lambda v: f"{v:.1f}",
            "orbit_type": lambda v: str(v),
        }

        for key, label in self._fields.items():
            value = data.get(key)
            if value is not None and key in formatters:
                try:
                    label.setText(formatters[key](value))
                except (ValueError, TypeError):
                    label.setText("--")
            else:
                label.setText("--")

    def clear(self) -> None:
        """Reset all fields."""
        self.name_label.setText("No satellite selected")
        self.norad_label.setText("")
        self.shadow_label.setText("")
        for label in self._fields.values():
            label.setText("--")
