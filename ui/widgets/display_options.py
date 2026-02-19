"""Display options widget: toggles for visual features."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
)


class DisplayOptionsWidget(QGroupBox):
    """Toggles for visual display features."""

    option_changed = pyqtSignal(str, object)  # (option_name, value)

    def __init__(self, parent=None):
        super().__init__("DISPLAY OPTIONS", parent)

        layout = QFormLayout()
        layout.setSpacing(8)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._toggles: dict[str, QCheckBox] = {}

        toggle_defs = [
            ("trails", "Orbit Trails", True),
            ("ground_tracks", "Ground Tracks", False),
            ("labels", "Labels", True),
            ("velocity_vectors", "Velocity Vectors", False),
            ("nadir_lines", "Nadir Lines", False),
            ("earth_texture", "Earth Texture", True),
            ("grid_axes", "Grid / Axes", False),
            ("terminator", "Day/Night Line", False),
        ]

        for key, label, default in toggle_defs:
            cb = QCheckBox()
            cb.setChecked(default)
            cb.toggled.connect(
                lambda checked, k=key: self.option_changed.emit(k, checked)
            )
            layout.addRow(label, cb)
            self._toggles[key] = cb

        # Separator label
        layout.addRow("", QLabel(""))

        # Orbit color mode dropdown
        self.color_mode = QComboBox()
        self.color_mode.addItems(["Solid Color", "By Altitude", "By Velocity"])
        self.color_mode.currentTextChanged.connect(
            lambda t: self.option_changed.emit("color_mode", t)
        )
        layout.addRow("Orbit Colors", self.color_mode)

        self.setLayout(layout)

    def get_option(self, key: str) -> bool:
        """Get current state of a toggle option."""
        if key in self._toggles:
            return self._toggles[key].isChecked()
        return False

    def set_option(self, key: str, value: bool) -> None:
        """Programmatically set a toggle option."""
        if key in self._toggles:
            self._toggles[key].setChecked(value)
