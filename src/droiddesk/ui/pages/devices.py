"""Devices page — Section 6.1. Live polling list, explicit unauthorized/offline
states (pairing instruction and reconnect action, not a raw error), wireless
debugging entry, and the Test Device Profile toggle. Rendered here against
`ui.static_data`; Phase 1 swaps the static rows for `DeviceService.devices_changed`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.ui import static_data
from droiddesk.ui.static_data import DeviceRow
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.status_pill import StatusDot, TagPill

_COLUMNS = ("", "Model", "Serial", "Android", "API", "ABI", "Link")


class DevicesPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        header = PageHeader(
            "Devices",
            "Polled every two seconds while this page is visible, every five when it is not.",
        )
        self._wifi_input = QLineEdit("192.168.1.24:5555")
        self._wifi_input.setFixedWidth(180)
        header.add_action(self._wifi_input)
        header.add_action(QPushButton("Connect over Wi-Fi"))
        header.add_action(QPushButton("↻  Refresh"))
        outer.addWidget(header)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)

        self._table = self._build_table()
        content_row.addWidget(self._table, 1)

        self._detail = self._build_detail(static_data.SELECTED_DEVICE)
        self._detail.setFixedWidth(280)
        content_row.addWidget(self._detail)

        outer.addLayout(content_row, 1)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.selectRow(0)

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(len(static_data.DEVICES), len(_COLUMNS))
        table.setHorizontalHeaderLabels(_COLUMNS)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 28)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for row, entry in enumerate(static_data.DEVICES):
            device = entry.device
            dot_cell = QWidget()
            dot_layout = QHBoxLayout(dot_cell)
            dot_layout.setContentsMargins(10, 0, 0, 0)
            dot_layout.addWidget(StatusDot(entry.dot))
            table.setCellWidget(row, 0, dot_cell)

            model_item = QTableWidgetItem(device.model or "(unknown)")
            model_item.setData(Qt.ItemDataRole.UserRole, entry)
            table.setItem(row, 1, model_item)
            table.setItem(row, 2, self._mono_item(device.serial))
            table.setItem(row, 3, QTableWidgetItem(device.android_version or "—"))
            table.setItem(
                row, 4, QTableWidgetItem(str(device.api_level) if device.api_level else "—")
            )
            table.setItem(row, 5, QTableWidgetItem(device.abi or "—"))
            table.setItem(row, 6, QTableWidgetItem(entry.link))

        return table

    def _mono_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setForeground(Qt.GlobalColor.cyan)
        return item

    def _build_detail(self, entry: DeviceRow) -> QWidget:
        card = Card()
        layout = card.body_layout()

        heading = QLabel("Device")
        heading.setProperty("role", "muted")
        layout.addWidget(heading)

        name = QLabel(entry.device.model or entry.device.serial)
        name.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(name)

        tags_row = QHBoxLayout()
        state_label = "Ready" if entry.device.state == "device" else entry.device.state.capitalize()
        tags_row.addWidget(TagPill(state_label))
        tags_row.addWidget(TagPill(entry.link))
        if entry.device.is_test_profile:
            tags_row.addWidget(TagPill("test device"))
        tags_row.addStretch(1)
        layout.addLayout(tags_row)

        layout.addWidget(self._section_label("PROPERTIES"))
        for label, value in [
            ("serial", entry.device.serial),
            ("release", entry.device.android_version or "—"),
            ("sdk", str(entry.device.api_level) if entry.device.api_level else "—"),
            ("abi", entry.device.abi or "—"),
            ("density", f"{entry.device.density}dpi" if entry.device.density else "—"),
        ]:
            layout.addLayout(self._property_row(label, value))

        layout.addWidget(self._section_label("TEST DEVICE PROFILE"))
        note = QLabel(static_data.TEST_DEVICE_PROFILE_NOTE)
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        layout.addWidget(note)

        layout.addStretch(1)

        layout.addWidget(QPushButton("Mark as test device"))
        layout.addWidget(QPushButton("≡  Open logcat"))
        layout.addWidget(QPushButton("↓  Take screenshot"))
        layout.addWidget(QPushButton("▶  Install an APK"))

        return card

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            "color: #5c5f66; font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-top: 6px;"
        )
        return label

    def _property_row(self, label: str, value: str) -> QHBoxLayout:
        row = QHBoxLayout()
        key = QLabel(label)
        key.setProperty("role", "muted")
        key.setFixedWidth(70)
        val = QLabel(value)
        val.setProperty("role", "mono")
        row.addWidget(key)
        row.addWidget(val, 1)
        return row

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        item = self._table.item(rows[0].row(), 1)
        entry = item.data(Qt.ItemDataRole.UserRole)
        new_detail = self._build_detail(entry)
        layout = self.layout()
        content_row = layout.itemAt(1).layout()
        old = content_row.itemAt(1).widget()
        content_row.replaceWidget(old, new_detail)
        old.setParent(None)
        old.deleteLater()
        new_detail.setFixedWidth(280)
        self._detail = new_detail

        # TODO(Phase 1): wire to DeviceService.devices_changed; render
        # unauthorized/offline rows distinctly with their recovery actions.
