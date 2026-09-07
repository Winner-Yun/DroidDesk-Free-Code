"""Devices page — Section 6.1. Live polling list, explicit unauthorized/offline
states (pairing instruction and reconnect action, not a raw error), wireless
debugging entry, and the Test Device Profile toggle.
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
from droiddesk.core.models import Device
from droiddesk.ui import static_data
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.status_pill import StatusDot, TagPill

_COLUMNS = ("", "Model", "Serial", "Android", "API", "ABI", "Link")

_STATE_DOT = {"device": "active", "unauthorized": "unauthorized", "offline": "offline"}
_STATE_LABEL = {"device": "Ready", "unauthorized": "Unauthorized", "offline": "Offline"}


def _link_type(serial: str) -> str:
    return "Wi-Fi" if ":" in serial else "USB"


class DevicesPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._selected_serial: str | None = None
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
        self._refresh_btn = QPushButton("↻  Refresh")
        header.add_action(self._wifi_input)
        header.add_action(QPushButton("Connect over Wi-Fi"))
        header.add_action(self._refresh_btn)
        outer.addWidget(header)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)

        self._table = self._build_table()
        content_row.addWidget(self._table, 1)

        self._detail = self._empty_detail()
        self._detail.setFixedWidth(280)
        content_row.addWidget(self._detail)

        outer.addLayout(content_row, 1)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        ctx.device_service.devices_changed.connect(self._repopulate)
        self._repopulate(ctx.device_service.devices())
        self._refresh_btn.clicked.connect(ctx.device_service.refresh)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._ctx.device_service.start_polling(page_visible=True)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._ctx.device_service.set_page_visible(False)

    def _repopulate(self, devices: list[Device]) -> None:
        self._table.setRowCount(len(devices))
        for row, device in enumerate(devices):
            dot_cell = QWidget()
            dot_layout = QHBoxLayout(dot_cell)
            dot_layout.setContentsMargins(10, 0, 0, 0)
            dot_layout.addWidget(StatusDot(_STATE_DOT.get(device.state, "ready")))
            self._table.setCellWidget(row, 0, dot_cell)

            model_item = QTableWidgetItem(device.model or "(unknown)")
            model_item.setData(Qt.ItemDataRole.UserRole, device)
            self._table.setItem(row, 1, model_item)
            self._table.setItem(row, 2, self._mono_item(device.serial))
            self._table.setItem(row, 3, QTableWidgetItem(device.android_version or "—"))
            self._table.setItem(
                row, 4, QTableWidgetItem(str(device.api_level) if device.api_level else "—")
            )
            self._table.setItem(row, 5, QTableWidgetItem(device.abi or "—"))
            self._table.setItem(row, 6, QTableWidgetItem(_link_type(device.serial)))

        self._restore_selection()

    def _restore_selection(self) -> None:
        if self._selected_serial:
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 1)
                if item and item.data(Qt.ItemDataRole.UserRole).serial == self._selected_serial:
                    self._table.selectRow(row)
                    return
        if self._table.rowCount():
            self._table.selectRow(0)
        else:
            self._swap_detail(self._empty_detail())

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(_COLUMNS))
        table.setHorizontalHeaderLabels(_COLUMNS)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 28)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        return table

    def _mono_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setForeground(Qt.GlobalColor.cyan)
        return item

    def _empty_detail(self) -> QWidget:
        card = Card()
        layout = card.body_layout()
        label = QLabel("No device selected")
        label.setProperty("role", "muted")
        layout.addWidget(label)
        layout.addStretch(1)
        return card

    def _build_detail(self, device: Device) -> QWidget:
        card = Card()
        layout = card.body_layout()

        heading = QLabel("Device")
        heading.setProperty("role", "muted")
        layout.addWidget(heading)

        name = QLabel(device.model or device.serial)
        name.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(name)

        tags_row = QHBoxLayout()
        tags_row.addWidget(TagPill(_STATE_LABEL.get(device.state, device.state.capitalize())))
        tags_row.addWidget(TagPill(_link_type(device.serial)))
        if device.is_test_profile:
            tags_row.addWidget(TagPill("test device"))
        tags_row.addStretch(1)
        layout.addLayout(tags_row)

        layout.addWidget(self._section_label("PROPERTIES"))
        for label, value in [
            ("serial", device.serial),
            ("release", device.android_version or "—"),
            ("sdk", str(device.api_level) if device.api_level else "—"),
            ("abi", device.abi or "—"),
            ("density", f"{device.density}dpi" if device.density else "—"),
        ]:
            layout.addLayout(self._property_row(label, value))

        layout.addWidget(self._section_label("TEST DEVICE PROFILE"))
        note = QLabel(static_data.TEST_DEVICE_PROFILE_NOTE)
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        layout.addWidget(note)

        layout.addStretch(1)

        if device.state == "offline":
            reconnect_btn = QPushButton("⟳  Reconnect")
            reconnect_btn.clicked.connect(
                lambda checked=False, s=device.serial: self._ctx.device_service.reconnect(s)
            )
            layout.addWidget(reconnect_btn)

        test_label = "Unmark test device" if device.is_test_profile else "Mark as test device"
        mark_btn = QPushButton(test_label)
        mark_btn.clicked.connect(
            lambda checked=False, d=device: self._ctx.device_service.mark_test_profile(
                d.serial, not d.is_test_profile
            )
        )
        layout.addWidget(mark_btn)
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
        if item is None:
            return
        device: Device = item.data(Qt.ItemDataRole.UserRole)
        self._selected_serial = device.serial
        self._swap_detail(self._build_detail(device))

    def _swap_detail(self, new_detail: QWidget) -> None:
        new_detail.setFixedWidth(280)
        content_row = self.layout().itemAt(1).layout()
        old = content_row.itemAt(1).widget()
        content_row.replaceWidget(old, new_detail)
        old.setParent(None)
        old.deleteLater()
        self._detail = new_detail
