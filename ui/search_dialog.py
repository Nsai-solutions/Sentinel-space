"""Celestrak satellite search dialog.

Allows users to search for satellites by name or NORAD ID,
browse predefined constellation groups, and add selected
satellites to the scene.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.tle_parser import TLEData, TLEManager, parse_tle_text
from utils.constants import CELESTRAK_BASE_URL, CELESTRAK_GROUPS
from utils.downloader import Downloader

logger = logging.getLogger(__name__)


class CelestrakWorker(QThread):
    """Background thread for Celestrak API queries."""

    results_ready = pyqtSignal(list)  # list[TLEData]
    error = pyqtSignal(str)

    def __init__(self, data_dir: Path, query: str = "", group: str = ""):
        super().__init__()
        self._data_dir = data_dir
        self._query = query
        self._group = group

    def run(self) -> None:
        try:
            downloader = Downloader(self._data_dir)
            tle_manager = TLEManager(self._data_dir, downloader)

            if self._group:
                tles = tle_manager.load_from_celestrak_group(
                    self._group, force_refresh=True
                )
            elif self._query.isdigit():
                tle = tle_manager.load_from_norad_id(int(self._query))
                tles = [tle] if tle else []
            else:
                tles = tle_manager.search_by_name(self._query)

            self.results_ready.emit(tles)

        except Exception as e:
            self.error.emit(str(e))


class CelestrakSearchDialog(QDialog):
    """Search Celestrak for satellites by name or NORAD ID."""

    satellites_added = pyqtSignal(list)  # list[TLEData]

    def __init__(self, parent=None, data_dir: Optional[Path] = None):
        super().__init__(parent)
        self.setWindowTitle("Search Celestrak")
        self.setMinimumSize(650, 550)
        self.setModal(True)

        self._data_dir = data_dir or Path(__file__).parent.parent / "data"
        self._results: list[TLEData] = []
        self._worker: Optional[CelestrakWorker] = None

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Search input row
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or NORAD ID...")
        self.search_input.returnPressed.connect(self._search)
        search_row.addWidget(self.search_input)

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("primaryButton")
        self.search_btn.setFixedWidth(100)
        self.search_btn.clicked.connect(self._search)
        search_row.addWidget(self.search_btn)

        layout.addLayout(search_row)

        # Constellation quick-load row
        constellation_row = QHBoxLayout()
        constellation_row.setSpacing(8)

        constellation_row.addWidget(QLabel("Constellation:"))
        self.constellation_combo = QComboBox()
        self.constellation_combo.addItem("-- Select Group --")
        for name in CELESTRAK_GROUPS:
            self.constellation_combo.addItem(name)
        constellation_row.addWidget(self.constellation_combo, stretch=1)

        self.load_group_btn = QPushButton("Load Group")
        self.load_group_btn.setFixedWidth(100)
        self.load_group_btn.clicked.connect(self._load_constellation)
        constellation_row.addWidget(self.load_group_btn)

        layout.addLayout(constellation_row)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(
            ["Select", "Name", "NORAD ID", "Inclination"]
        )
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(0, 60)
        self.results_table.setColumnWidth(2, 100)
        self.results_table.setColumnWidth(3, 100)
        self.results_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.results_table)

        # Bottom row: status + action buttons
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("unitLabel")
        bottom_row.addWidget(self.status_label)
        bottom_row.addStretch()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setFixedWidth(90)
        self.select_all_btn.clicked.connect(self._select_all)
        bottom_row.addWidget(self.select_all_btn)

        self.add_btn = QPushButton("Add Selected")
        self.add_btn.setObjectName("primaryButton")
        self.add_btn.setFixedWidth(120)
        self.add_btn.clicked.connect(self._add_selected)
        bottom_row.addWidget(self.add_btn)

        cancel_btn = QPushButton("Close")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.accept)
        bottom_row.addWidget(cancel_btn)

        layout.addLayout(bottom_row)

    def _search(self) -> None:
        """Query Celestrak API in a background thread."""
        query = self.search_input.text().strip()
        if not query:
            return

        self._set_loading(True)
        self.status_label.setText("Searching...")

        self._worker = CelestrakWorker(self._data_dir, query=query)
        self._worker.results_ready.connect(self._populate_results)
        self._worker.error.connect(self._on_search_error)
        self._worker.start()

    def _load_constellation(self) -> None:
        """Load a predefined constellation group."""
        idx = self.constellation_combo.currentIndex()
        if idx <= 0:
            return

        group_name = self.constellation_combo.currentText()
        self._set_loading(True)
        self.status_label.setText(f"Loading {group_name}...")

        self._worker = CelestrakWorker(self._data_dir, group=group_name)
        self._worker.results_ready.connect(self._populate_results)
        self._worker.error.connect(self._on_search_error)
        self._worker.start()

    def _populate_results(self, tles: list[TLEData]) -> None:
        """Fill the results table with TLE data."""
        self._set_loading(False)
        self._results = tles

        self.results_table.setRowCount(len(tles))

        for row, tle in enumerate(tles):
            # Checkbox
            cb_item = QTableWidgetItem()
            cb_item.setFlags(
                cb_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.results_table.setItem(row, 0, cb_item)

            # Name
            name_item = QTableWidgetItem(tle.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.results_table.setItem(row, 1, name_item)

            # NORAD ID
            id_item = QTableWidgetItem(str(tle.catalog_number))
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.results_table.setItem(row, 2, id_item)

            # Inclination
            inc_item = QTableWidgetItem(f"{tle.inclination:.2f}")
            inc_item.setFlags(inc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.results_table.setItem(row, 3, inc_item)

        self.status_label.setText(f"Found {len(tles)} satellites")

    def _on_search_error(self, error_msg: str) -> None:
        """Handle search errors."""
        self._set_loading(False)
        self.status_label.setText(f"Error: {error_msg}")
        logger.error("Celestrak search error: %s", error_msg)

    def _select_all(self) -> None:
        """Select all results."""
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _add_selected(self) -> None:
        """Add checked satellites and close."""
        selected_tles: list[TLEData] = []

        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                if row < len(self._results):
                    selected_tles.append(self._results[row])

        if selected_tles:
            self.satellites_added.emit(selected_tles)
            self.status_label.setText(f"Added {len(selected_tles)} satellites")

    def _set_loading(self, loading: bool) -> None:
        """Enable/disable UI during loading."""
        self.search_btn.setEnabled(not loading)
        self.load_group_btn.setEnabled(not loading)
        self.search_input.setEnabled(not loading)
        self.constellation_combo.setEnabled(not loading)
