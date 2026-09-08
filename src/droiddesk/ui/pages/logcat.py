"""Logcat page — Section 6.4. LogcatModel-backed table view with a filter
toolbar (level/tag/PID/regex) and pause control. Seeded from
`static_data.LOGCAT_LINES` through the real `LogcatModel.queue()` /
`parse_threadtime` path so the column layout and parsing are already proven
out before Phase 2 wires in a live `AdbStream`.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.infra.process import AdbStream
from droiddesk.ui import static_data
from droiddesk.ui.models.logcat_model import LogcatModel
from droiddesk.ui.widgets.card import PageHeader

_PRIORITY_COLORS = {"E": "#e05a4d", "W": "#f1c40f", "I": "#5b9bd5", "D": "#8b8e94", "V": "#5c5f66"}

class LogcatFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = "V"
        self._tag = ""
        self._pid = ""
        self._regex = None
        
        self._levels = {"V": 0, "D": 1, "I": 2, "W": 3, "E": 4, "F": 5}

    def set_filters(self, level: str, tag: str, pid: str, regex_str: str):
        self._level = level
        self._tag = tag.strip().lower()
        self._pid = pid.strip()
        if regex_str:
            try:
                self._regex = re.compile(regex_str, re.IGNORECASE)
            except re.error:
                self._regex = None
        else:
            self._regex = None
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not model:
            return True
            
        priority = model.index(source_row, 3, source_parent).data()
        if self._levels.get(priority, 0) < self._levels.get(self._level, 0):
            return False
            
        if self._tag:
            tag = model.index(source_row, 4, source_parent).data()
            if self._tag not in str(tag).lower():
                return False
                
        if self._pid:
            pid = model.index(source_row, 1, source_parent).data()
            if str(pid) != self._pid:
                return False
                
        if self._regex:
            message = model.index(source_row, 5, source_parent).data()
            if not self._regex.search(str(message)):
                return False
                
        return True


class LogcatPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.setProperty("role", "page")
        
        self._model = LogcatModel()
        self._proxy = LogcatFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        
        self._stream: AdbStream | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "Logcat",
            "Streamed from the selected device and parsed into columns. Pausing holds the view without dropping the stream.",
        )
        
        self._device_combo = QComboBox()
        self._device_combo.setFixedWidth(200)
        self._update_device_combo()
        self._ctx.device_service.devices_changed.connect(self._update_device_combo)
        header.add_action(self._device_combo)
        
        self._pause_button = QPushButton("⏸  Pause")
        self._pause_button.setCheckable(True)
        self._pause_button.toggled.connect(self._on_pause_toggled)
        header.add_action(self._pause_button)
        
        clear_button = QPushButton("✕  Clear")
        clear_button.clicked.connect(self._model.clear)
        header.add_action(clear_button)
        
        header.add_action(QPushButton("↓  Export view"))
        
        self._stream_button = QPushButton("Start stream")
        self._stream_button.setProperty("role", "primary")
        self._stream_button.setCheckable(True)
        self._stream_button.toggled.connect(self._on_stream_toggled)
        header.add_action(self._stream_button)
        
        outer.addWidget(header)
        outer.addLayout(self._build_filter_row())

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        header_view = self._table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self._table, 1)

        for line in static_data.LOGCAT_LINES:
            self._model.queue(line)
        self._model._flush()

    def _update_device_combo(self) -> None:
        current_data = self._device_combo.currentData()
        self._device_combo.clear()
        devices = self._ctx.device_service.devices()
        
        if not devices:
            self._device_combo.addItem("No devices connected")
            self._device_combo.setEnabled(False)
        else:
            for d in devices:
                self._device_combo.addItem(d.serial, d.serial)
            self._device_combo.setEnabled(True)
            
            # restore selection if possible
            if current_data:
                idx = self._device_combo.findData(current_data)
                if idx >= 0:
                    self._device_combo.setCurrentIndex(idx)

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._level_combo = QComboBox()
        self._level_combo.addItems(["V", "D", "I", "W", "E"])
        self._level_combo.setFixedWidth(56)
        self._level_combo.currentTextChanged.connect(self._apply_filters)
        row.addWidget(self._level_combo)

        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("Tag")
        self._tag_input.setFixedWidth(140)
        self._tag_input.textChanged.connect(self._apply_filters)
        row.addWidget(self._tag_input)

        self._pid_input = QLineEdit()
        self._pid_input.setPlaceholderText("PID")
        self._pid_input.setFixedWidth(90)
        self._pid_input.textChanged.connect(self._apply_filters)
        row.addWidget(self._pid_input)

        self._regex_input = QLineEdit()
        self._regex_input.setPlaceholderText("Regular expression over the message column")
        self._regex_input.textChanged.connect(self._apply_filters)
        row.addWidget(self._regex_input, 1)

        self._count_label = QLabel(f"{self._model.rowCount()} lines")
        self._count_label.setProperty("role", "muted")
        row.addWidget(self._count_label)
        
        self._model.modelReset.connect(self._update_count)
        self._model.rowsInserted.connect(self._update_count)

        return row

    def _update_count(self) -> None:
        self._count_label.setText(f"{self._model.rowCount()} lines")

    def _apply_filters(self) -> None:
        self._proxy.set_filters(
            self._level_combo.currentText(),
            self._tag_input.text(),
            self._pid_input.text(),
            self._regex_input.text()
        )

    def _on_pause_toggled(self, paused: bool) -> None:
        self._model.set_paused(paused)
        self._pause_button.setText("▶  Resume" if paused else "⏸  Pause")

    def _on_stream_toggled(self, checked: bool) -> None:
        if checked:
            serial = self._device_combo.currentData()
            if not serial:
                self._stream_button.setChecked(False)
                return
            
            self._stream_button.setText("Stop stream")
            
            self._stream = self._ctx.device_service._adb.logcat_stream(serial)
            self._stream.line_received.connect(self._model.queue)
            self._stream.finished.connect(self._on_stream_finished)
            self._stream.start()
        else:
            self._stream_button.setText("Start stream")
            if self._stream:
                self._stream.stop()
                self._stream = None

    def _on_stream_finished(self) -> None:
        self._stream_button.setChecked(False)
        self._stream_button.setText("Start stream")
        self._stream = None
