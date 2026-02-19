"""Right sidebar containing satellite list, time controls, display options, and info panel."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.info_panel import InfoPanelWidget
from ui.widgets.display_options import DisplayOptionsWidget
from ui.widgets.satellite_list import SatelliteListWidget
from ui.widgets.time_controls import TimeControlsWidget


class SidebarWidget(QFrame):
    """Right sidebar assembling all control widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area for all content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(16)

        # Sub-widgets
        self.satellite_list = SatelliteListWidget()
        content_layout.addWidget(self.satellite_list)

        self.time_controls = TimeControlsWidget()
        content_layout.addWidget(self.time_controls)

        self.display_options = DisplayOptionsWidget()
        content_layout.addWidget(self.display_options)

        self.info_panel = InfoPanelWidget()
        content_layout.addWidget(self.info_panel)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)
