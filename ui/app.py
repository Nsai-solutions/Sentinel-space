"""Main application window for the Orbital Propagator.

Contains the QMainWindow with embedded PyVista 3D viewport,
sidebar controls, menu bar, status bar, keyboard shortcuts,
and the SimulationController that drives the animation loop.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenuBar,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from pyvistaqt import QtInteractor

from core.tle_parser import TLEData, TLEManager, parse_tle_text
from ui.sidebar import SidebarWidget
from utils.constants import SATELLITE_COLORS
from visualization.scene import OrbitalScene

logger = logging.getLogger(__name__)


class SimulationController(QObject):
    """Drives the simulation clock and triggers rendering updates."""

    time_updated = pyqtSignal(object)  # emits datetime

    def __init__(self, scene: OrbitalScene, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.sim_time = datetime.now(timezone.utc)
        self.warp_factor = 1.0
        self._is_playing = False
        self._last_wall_time = 0.0
        self._frame_count = 0
        self._fps_timer = 0.0
        self._current_fps = 0.0

        # Render timer: 33ms = ~30 FPS
        self.render_timer = QTimer()
        self.render_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.render_timer.timeout.connect(self._tick)
        self.render_timer.setInterval(33)

    def play(self) -> None:
        """Start the simulation."""
        self._is_playing = True
        self._last_wall_time = time.perf_counter()
        self._fps_timer = self._last_wall_time
        self._frame_count = 0
        self.render_timer.start()

    def pause(self) -> None:
        """Pause the simulation."""
        self._is_playing = False
        self.render_timer.stop()

    def toggle_play_pause(self) -> None:
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def set_warp(self, factor: float) -> None:
        """Set time warp factor."""
        self.warp_factor = max(1.0, min(factor, 10000.0))

    def increase_warp(self) -> None:
        """Double the warp factor."""
        self.set_warp(self.warp_factor * 2)

    def decrease_warp(self) -> None:
        """Halve the warp factor."""
        self.set_warp(self.warp_factor / 2)

    def reset_to_now(self) -> None:
        """Reset simulation time to current UTC."""
        self.sim_time = datetime.now(timezone.utc)
        self.time_updated.emit(self.sim_time)
        self.scene.update(self.sim_time)

    def jump_to_time(self, dt: datetime) -> None:
        """Jump to a specific time."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        self.sim_time = dt
        self.time_updated.emit(self.sim_time)
        self.scene.update(self.sim_time)

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def fps(self) -> float:
        return self._current_fps

    def _tick(self) -> None:
        """Called every 33ms by QTimer."""
        now = time.perf_counter()
        wall_dt = now - self._last_wall_time
        self._last_wall_time = now

        # FPS tracking
        self._frame_count += 1
        if now - self._fps_timer >= 1.0:
            self._current_fps = self._frame_count / (now - self._fps_timer)
            self._fps_timer = now
            self._frame_count = 0

        # Advance simulation time
        sim_dt = wall_dt * self.warp_factor
        self.sim_time += timedelta(seconds=sim_dt)

        # Update scene
        self.scene.update(self.sim_time)
        self.time_updated.emit(self.sim_time)


class OrbitalPropagatorApp(QMainWindow):
    """Main application window."""

    def __init__(self, data_dir: Optional[Path] = None):
        super().__init__()
        self.setWindowTitle("Orbital Propagator")
        self.setMinimumSize(1280, 800)
        self.resize(1600, 1000)

        self._data_dir = data_dir or Path(__file__).parent.parent / "data"
        self._selected_sat_id: Optional[str] = None

        # Build UI
        self._build_layout()
        self._setup_menus()
        self._setup_status_bar()
        self._setup_shortcuts()

        # Initialize scene
        self.scene = OrbitalScene(self.plotter)
        self.scene.initialize()

        # Simulation controller
        self.sim_controller = SimulationController(self.scene, self)

        # Wire signals
        self._connect_signals()

    def _build_layout(self) -> None:
        """Create the main layout: viewport + sidebar."""
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 3D Viewport
        viewport_frame = QFrame()
        viewport_frame.setObjectName("viewportFrame")
        viewport_layout = QVBoxLayout(viewport_frame)
        viewport_layout.setContentsMargins(0, 0, 0, 0)

        self.plotter = QtInteractor(viewport_frame)
        viewport_layout.addWidget(self.plotter.interactor)

        main_layout.addWidget(viewport_frame, stretch=3)

        # Sidebar
        self.sidebar = SidebarWidget()
        main_layout.addWidget(self.sidebar)

        self.setCentralWidget(central)

    def _setup_menus(self) -> None:
        """Create menu bar."""
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        load_tle = QAction("&Load TLE File...", self)
        load_tle.setShortcut(QKeySequence("Ctrl+O"))
        load_tle.triggered.connect(self._load_tle_file)
        file_menu.addAction(load_tle)

        search_action = QAction("&Search Celestrak...", self)
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        search_action.triggered.connect(self._open_search_dialog)
        file_menu.addAction(search_action)

        file_menu.addSeparator()

        screenshot_action = QAction("Export &Screenshot...", self)
        screenshot_action.setShortcut(QKeySequence("Ctrl+S"))
        screenshot_action.triggered.connect(self._export_screenshot)
        file_menu.addAction(screenshot_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menu_bar.addMenu("&View")

        self.trails_action = QAction("Orbit &Trails", self, checkable=True, checked=True)
        self.trails_action.toggled.connect(
            lambda v: self.scene.orbits.toggle_all(v) if hasattr(self, "scene") else None
        )
        view_menu.addAction(self.trails_action)

        self.labels_action = QAction("&Labels", self, checkable=True, checked=True)
        self.labels_action.toggled.connect(
            lambda v: self.scene.satellites.toggle_labels(v) if hasattr(self, "scene") else None
        )
        view_menu.addAction(self.labels_action)

        self.ground_track_action = QAction("&Ground Tracks", self, checkable=True)
        self.ground_track_action.toggled.connect(
            lambda v: self.scene.toggle_ground_tracks(v) if hasattr(self, "scene") else None
        )
        view_menu.addAction(self.ground_track_action)

        view_menu.addSeparator()

        axes_action = QAction("ECI &Axes", self, checkable=True)
        axes_action.toggled.connect(
            lambda v: self.scene.toggle_axes(v) if hasattr(self, "scene") else None
        )
        view_menu.addAction(axes_action)

        grid_action = QAction("Equatorial &Grid", self, checkable=True)
        grid_action.toggled.connect(
            lambda v: self.scene.toggle_equatorial_grid(v) if hasattr(self, "scene") else None
        )
        view_menu.addAction(grid_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        shortcuts_action = QAction("&Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

    def _setup_status_bar(self) -> None:
        """Create status bar."""
        self.status_bar = self.statusBar()

        self.time_status_label = QLabel("Sim Time: --")
        self.status_bar.addWidget(self.time_status_label, stretch=2)

        self.selected_status_label = QLabel("Selected: None")
        self.status_bar.addWidget(self.selected_status_label, stretch=1)

        self.fps_label = QLabel("-- FPS")
        self.status_bar.addPermanentWidget(self.fps_label)

        self.status_label = QLabel("Ready")
        self.status_bar.addPermanentWidget(self.status_label)

    def _setup_shortcuts(self) -> None:
        """Create keyboard shortcuts."""
        shortcuts = {
            "Space": self._toggle_play_pause,
            "+": lambda: self.sim_controller.increase_warp(),
            "=": lambda: self.sim_controller.increase_warp(),
            "-": lambda: self.sim_controller.decrease_warp(),
            "R": lambda: self.sim_controller.reset_to_now(),
            "F": self._focus_selected,
            "G": lambda: self.ground_track_action.toggle(),
            "T": lambda: self.trails_action.toggle(),
            "L": lambda: self.labels_action.toggle(),
        }
        for key, callback in shortcuts.items():
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)

    def _connect_signals(self) -> None:
        """Wire up all signals between components."""
        # Time controls -> SimulationController
        self.sidebar.time_controls.play_toggled.connect(self._on_play_toggled)
        self.sidebar.time_controls.warp_changed.connect(self.sim_controller.set_warp)
        self.sidebar.time_controls.time_jumped.connect(self.sim_controller.jump_to_time)

        # SimulationController -> UI updates
        self.sim_controller.time_updated.connect(self._on_time_updated)

        # Satellite list -> Scene
        self.sidebar.satellite_list.satellite_toggled.connect(
            lambda sid, vis: self.scene.set_satellite_visible(sid, vis)
        )
        self.sidebar.satellite_list.satellite_selected.connect(self._on_satellite_selected)
        self.sidebar.satellite_list.satellite_double_clicked.connect(
            lambda sid: self.scene.focus_on_satellite(sid)
        )

        # Display options -> Scene
        self.sidebar.display_options.option_changed.connect(self._on_display_option_changed)

    def add_satellites_from_tle(self, tles: list[TLEData]) -> None:
        """Add multiple satellites from parsed TLE data."""
        self.status_label.setText(f"Loading {len(tles)} satellites...")

        for tle in tles:
            sat_id = self.scene.add_satellite(tle)
            if sat_id:
                self.sidebar.satellite_list.add_satellite(
                    sat_id, tle.name
                )

        self.status_label.setText(f"Loaded {len(tles)} satellites")

    def load_default_satellites(self) -> None:
        """Load sample TLE data for first-run experience."""
        self.status_label.setText("Loading sample satellites...")

        tle_manager = TLEManager(self._data_dir)
        tles = tle_manager.load_sample_tles()

        if tles:
            self.add_satellites_from_tle(tles)
            logger.info("Loaded %d sample satellites", len(tles))
        else:
            logger.warning("No sample TLEs found")
            self.status_label.setText("No sample TLE data available")

    # --- Event Handlers ---

    def _toggle_play_pause(self) -> None:
        self.sim_controller.toggle_play_pause()
        self.sidebar.time_controls.set_playing(self.sim_controller.is_playing)

    def _on_play_toggled(self, playing: bool) -> None:
        if playing:
            self.sim_controller.play()
        else:
            self.sim_controller.pause()

    def _on_time_updated(self, sim_time: datetime) -> None:
        """Update UI elements with new simulation time."""
        self.sidebar.time_controls.update_time_display(sim_time)
        self.time_status_label.setText(
            f"Sim Time: {sim_time.strftime('%Y/%m/%d %H:%M:%S')} UTC"
        )
        self.fps_label.setText(f"{self.sim_controller.fps:.0f} FPS")

        # Update info panel for selected satellite
        if self._selected_sat_id:
            data = self.scene.get_satellite_data(self._selected_sat_id, sim_time)
            if data:
                self.sidebar.info_panel.update_data(data)

    def _on_satellite_selected(self, sat_id: str) -> None:
        """Handle satellite selection."""
        self._selected_sat_id = sat_id
        self.scene.satellites.select(sat_id)
        self.selected_status_label.setText(
            f"Selected: {self.scene._tle_data.get(sat_id, type('', (), {'name': sat_id})()).name if sat_id in self.scene._tle_data else sat_id}"
        )

        # Immediately update info panel
        data = self.scene.get_satellite_data(sat_id, self.sim_controller.sim_time)
        if data:
            self.sidebar.info_panel.update_data(data)
            self.selected_status_label.setText(f"Selected: {data['name']}")

    def _on_display_option_changed(self, key: str, value: object) -> None:
        """Handle display option toggles."""
        if key == "trails":
            self.scene.orbits.toggle_all(bool(value))
            self.trails_action.setChecked(bool(value))
        elif key == "ground_tracks":
            self.scene.toggle_ground_tracks(bool(value))
            self.ground_track_action.setChecked(bool(value))
        elif key == "labels":
            self.scene.satellites.toggle_labels(bool(value))
            self.labels_action.setChecked(bool(value))
        elif key == "velocity_vectors":
            self.scene.satellites.toggle_velocity_vectors(bool(value))
        elif key == "nadir_lines":
            self.scene.satellites.toggle_nadir_lines(bool(value))
        elif key == "grid_axes":
            self.scene.toggle_axes(bool(value))
            self.scene.toggle_equatorial_grid(bool(value))
        elif key == "terminator":
            self.scene.toggle_terminator(bool(value))
        elif key == "color_mode":
            mode_map = {
                "Solid Color": "solid",
                "By Altitude": "altitude",
                "By Velocity": "velocity",
            }
            self.scene.orbits.set_color_mode(mode_map.get(str(value), "solid"))

    def _focus_selected(self) -> None:
        """Focus camera on selected satellite."""
        if self._selected_sat_id:
            self.scene.focus_on_satellite(self._selected_sat_id)

    def _load_tle_file(self) -> None:
        """Open file dialog to load TLE data."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Load TLE File",
            "",
            "TLE Files (*.tle *.txt);;All Files (*)",
        )
        if filepath:
            try:
                text = Path(filepath).read_text(encoding="utf-8")
                tles = parse_tle_text(text)
                if tles:
                    self.add_satellites_from_tle(tles)
                else:
                    self.status_label.setText("No valid TLEs found in file")
            except Exception as e:
                logger.error("Failed to load TLE file: %s", e)
                self.status_label.setText(f"Error: {e}")

    def _open_search_dialog(self) -> None:
        """Open the Celestrak search dialog."""
        from ui.search_dialog import CelestrakSearchDialog

        dialog = CelestrakSearchDialog(self, self._data_dir)
        dialog.satellites_added.connect(self.add_satellites_from_tle)
        dialog.exec()

    def _export_screenshot(self) -> None:
        """Save a screenshot of the 3D viewport."""
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Screenshot",
            "orbital_propagator.png",
            "PNG Images (*.png);;All Files (*)",
        )
        if filepath:
            try:
                self.plotter.screenshot(filepath)
                self.status_label.setText(f"Screenshot saved: {filepath}")
            except Exception as e:
                logger.error("Failed to save screenshot: %s", e)

    def _show_about(self) -> None:
        """Show about dialog."""
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "About Orbital Propagator",
            "Orbital Propagator v1.0\n\n"
            "A real-time satellite orbit visualization tool.\n"
            "Uses SGP4 propagation with real TLE data.\n\n"
            "Built with PyQt6, PyVista, and sgp4.",
        )

    def _show_shortcuts(self) -> None:
        """Show keyboard shortcuts dialog."""
        from PyQt6.QtWidgets import QMessageBox

        text = (
            "Keyboard Shortcuts:\n\n"
            "Space    - Play / Pause\n"
            "+  /  =  - Speed up time warp\n"
            "-        - Slow down time warp\n"
            "R        - Reset to real-time\n"
            "F        - Focus on selected satellite\n"
            "T        - Toggle orbit trails\n"
            "G        - Toggle ground tracks\n"
            "L        - Toggle labels\n\n"
            "Ctrl+O   - Load TLE file\n"
            "Ctrl+F   - Search Celestrak\n"
            "Ctrl+S   - Export screenshot\n"
            "Ctrl+Q   - Exit"
        )
        QMessageBox.information(self, "Keyboard Shortcuts", text)

    def closeEvent(self, event) -> None:
        """Clean up on close."""
        self.sim_controller.pause()
        self.plotter.close()
        super().closeEvent(event)
