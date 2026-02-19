"""Time controls widget: play/pause, time warp, and time display."""

from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)


class TimeControlsWidget(QGroupBox):
    """Play/pause, time warp slider, time display, Jump to Now."""

    play_toggled = pyqtSignal(bool)  # True = playing
    warp_changed = pyqtSignal(float)  # warp factor
    time_jumped = pyqtSignal(object)  # datetime to jump to

    WARP_STEPS = [1, 2, 5, 10, 50, 100, 500, 1000, 5000, 10000]

    def __init__(self, parent=None):
        super().__init__("TIME CONTROLS", parent)
        self._is_playing = False

        layout = QVBoxLayout()
        layout.setSpacing(8)

        # Row 1: Play/Pause + Warp display
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.play_btn = QPushButton("Play")
        self.play_btn.setObjectName("primaryButton")
        self.play_btn.setFixedWidth(80)
        self.play_btn.setFixedHeight(36)
        self.play_btn.clicked.connect(self._toggle_play)
        row1.addWidget(self.play_btn)

        self.warp_label = QLabel("1x")
        self.warp_label.setObjectName("valueLabel")
        self.warp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.warp_label.setMinimumWidth(80)
        row1.addWidget(self.warp_label)

        layout.addLayout(row1)

        # Row 2: Warp slider
        slider_row = QHBoxLayout()
        slider_row.setSpacing(8)

        slow_label = QLabel("1x")
        slow_label.setObjectName("unitLabel")
        slider_row.addWidget(slow_label)

        self.warp_slider = QSlider(Qt.Orientation.Horizontal)
        self.warp_slider.setRange(0, len(self.WARP_STEPS) - 1)
        self.warp_slider.setValue(0)
        self.warp_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.warp_slider.setTickInterval(1)
        self.warp_slider.valueChanged.connect(self._on_warp_change)
        slider_row.addWidget(self.warp_slider)

        fast_label = QLabel("10000x")
        fast_label.setObjectName("unitLabel")
        slider_row.addWidget(fast_label)

        layout.addLayout(slider_row)

        # Row 3: Current simulation time
        self.time_display = QLabel("----/--/-- --:--:-- UTC")
        self.time_display.setObjectName("valueLabel")
        self.time_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.time_display)

        # Row 4: Jump to Now
        self.now_btn = QPushButton("Jump to Now")
        self.now_btn.setFixedHeight(32)
        self.now_btn.clicked.connect(self._jump_to_now)
        layout.addWidget(self.now_btn)

        self.setLayout(layout)

    def update_time_display(self, sim_time: datetime) -> None:
        """Update the displayed simulation time."""
        if sim_time.tzinfo is None:
            sim_time = sim_time.replace(tzinfo=timezone.utc)
        self.time_display.setText(
            sim_time.strftime("%Y/%m/%d %H:%M:%S UTC")
        )

    def set_playing(self, playing: bool) -> None:
        """Update the play button state."""
        self._is_playing = playing
        self.play_btn.setText("Pause" if playing else "Play")

    def _toggle_play(self) -> None:
        self._is_playing = not self._is_playing
        self.play_btn.setText("Pause" if self._is_playing else "Play")
        self.play_toggled.emit(self._is_playing)

    def _on_warp_change(self, index: int) -> None:
        factor = self.WARP_STEPS[index]
        self.warp_label.setText(f"{factor}x")
        self.warp_changed.emit(float(factor))

    def _jump_to_now(self) -> None:
        now = datetime.now(timezone.utc)
        self.time_jumped.emit(now)

    @property
    def current_warp(self) -> float:
        return float(self.WARP_STEPS[self.warp_slider.value()])
