"""Satellite list widget with checkboxes, search, and categories."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class SatelliteListWidget(QGroupBox):
    """Scrollable satellite list with checkboxes and search/filter."""

    satellite_toggled = pyqtSignal(str, bool)  # (sat_id, visible)
    satellite_selected = pyqtSignal(str)  # sat_id
    satellite_double_clicked = pyqtSignal(str)  # sat_id (focus camera)

    def __init__(self, parent=None):
        super().__init__("SATELLITES", parent)

        layout = QVBoxLayout()
        layout.setSpacing(8)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter satellites...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter)
        layout.addWidget(self.search_input)

        # Satellite list
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(150)
        self.list_widget.setMaximumHeight(300)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.itemChanged.connect(self._on_item_checked)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list_widget)

        # Quick actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.select_all_btn = QPushButton("All")
        self.select_all_btn.setFixedHeight(28)
        self.select_all_btn.clicked.connect(self._select_all)
        btn_row.addWidget(self.select_all_btn)

        self.select_none_btn = QPushButton("None")
        self.select_none_btn.setFixedHeight(28)
        self.select_none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(self.select_none_btn)

        layout.addLayout(btn_row)
        self.setLayout(layout)

        self._sat_items: dict[str, QListWidgetItem] = {}

    def add_satellite(
        self, sat_id: str, name: str, category: str = ""
    ) -> None:
        """Add a satellite to the list."""
        display_text = name
        if category:
            display_text = f"[{category}] {name}"

        item = QListWidgetItem(display_text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        item.setData(Qt.ItemDataRole.UserRole, sat_id)
        item.setData(Qt.ItemDataRole.UserRole + 1, name)
        item.setData(Qt.ItemDataRole.UserRole + 2, category)

        self.list_widget.addItem(item)
        self._sat_items[sat_id] = item

    def remove_satellite(self, sat_id: str) -> None:
        """Remove a satellite from the list."""
        if sat_id in self._sat_items:
            item = self._sat_items[sat_id]
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
            del self._sat_items[sat_id]

    def highlight_satellite(self, sat_id: str) -> None:
        """Programmatically select a satellite in the list."""
        if sat_id in self._sat_items:
            item = self._sat_items[sat_id]
            self.list_widget.blockSignals(True)
            self.list_widget.setCurrentItem(item)
            self.list_widget.blockSignals(False)

    def get_selected_id(self) -> str | None:
        """Get the currently selected satellite ID."""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _filter(self, text: str) -> None:
        """Filter satellites by search text."""
        text_lower = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            name = item.data(Qt.ItemDataRole.UserRole + 1) or ""
            category = item.data(Qt.ItemDataRole.UserRole + 2) or ""
            visible = (
                text_lower in name.lower()
                or text_lower in category.lower()
                or not text
            )
            item.setHidden(not visible)

    def _on_selection_changed(
        self, current: QListWidgetItem, previous: QListWidgetItem
    ) -> None:
        """Handle satellite selection change."""
        if current:
            sat_id = current.data(Qt.ItemDataRole.UserRole)
            if sat_id:
                self.satellite_selected.emit(sat_id)

    def _on_item_checked(self, item: QListWidgetItem) -> None:
        """Handle checkbox toggle."""
        sat_id = item.data(Qt.ItemDataRole.UserRole)
        checked = item.checkState() == Qt.CheckState.Checked
        if sat_id:
            self.satellite_toggled.emit(sat_id, checked)

    def _on_double_click(self, item: QListWidgetItem) -> None:
        """Handle double-click to focus camera."""
        sat_id = item.data(Qt.ItemDataRole.UserRole)
        if sat_id:
            self.satellite_double_clicked.emit(sat_id)

    def _select_all(self) -> None:
        """Check all visible satellites."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked)

    def _select_none(self) -> None:
        """Uncheck all visible satellites."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Unchecked)
