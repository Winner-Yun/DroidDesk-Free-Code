"""Logcat page providing structured live streaming, level filtering, and log search."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import override

from PySide6.QtCore import QModelIndex, QObject, QPersistentModelIndex, QSize, QSortFilterProxyModel
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.infra.process import AdbStream
from droiddesk.ui.models.logcat_model import LogcatModel
from droiddesk.ui.theme import TEXT_MUTED, get_icon
from droiddesk.ui.widgets.card import PageHeader

_PRIORITY_COLORS = {"E": "#e05a4d", "W": "#f1c40f", "I": "#5b9bd5", "D": "#8b8e94", "V": "#5c5f66"}


class LogcatFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._level = "V"
        self._tag = ""
        self._pid = ""
        self._regex: re.Pattern[str] | None = None
        self._levels = {"V": 0, "D": 1, "I": 2, "W": 3, "E": 4, "F": 5}

    def set_filters(self, level: str, tag: str, pid: str, regex_str: str) -> None:
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
        self.invalidate()

    @override
    def filterAcceptsRow(
        self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
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
            "Streamed from the selected device and parsed into columns. "
            "Pausing holds the view without dropping the stream.",
        )

        self._device_combo = QComboBox()
        self._device_combo.setFixedWidth(200)

        self._pause_button = QPushButton("Pause")
        self._pause_button.setIcon(get_icon("pause", size=13, color=TEXT_MUTED))
        self._pause_button.setIconSize(QSize(13, 13))
        self._pause_button.setCheckable(True)
        self._pause_button.toggled.connect(self._on_pause_toggled)

        self._clear_button = QPushButton("Clear")
        self._clear_button.setIcon(get_icon("trash-2", size=13, color=TEXT_MUTED))
        self._clear_button.setIconSize(QSize(13, 13))
        self._clear_button.clicked.connect(self._on_clear_clicked)

        self._export_button = QPushButton("Export view")
        self._export_button.setIcon(get_icon("file-down", size=13, color=TEXT_MUTED))
        self._export_button.setIconSize(QSize(13, 13))
        self._export_button.clicked.connect(self._on_export_clicked)

        self._stream_button = QPushButton("Start stream")
        self._stream_button.setProperty("role", "primary")
        self._stream_button.setIcon(get_icon("play", size=13, color="#ffffff"))
        self._stream_button.setIconSize(QSize(13, 13))
        self._stream_button.setCheckable(True)
        self._stream_button.toggled.connect(self._on_stream_toggled)

        self._update_device_combo()
        self._device_combo.currentIndexChanged.connect(self._update_button_states)
        self._ctx.device_service.devices_changed.connect(self._update_device_combo)

        header.add_action(self._device_combo)
        header.add_action(self._pause_button)
        header.add_action(self._clear_button)
        header.add_action(self._export_button)
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

        self._update_button_states()

    def _update_device_combo(self) -> None:
        current_data = self._device_combo.currentData()
        self._device_combo.clear()
        devices = self._ctx.device_service.devices()

        is_streaming = self._stream is not None
        if not devices:
            self._device_combo.addItem("No emulator connected")
            self._device_combo.setEnabled(False)
        else:
            for d in devices:
                self._device_combo.addItem(d.serial, d.serial)
            self._device_combo.setEnabled(not is_streaming)

            # restore selection if possible
            if current_data:
                idx = self._device_combo.findData(current_data)
                if idx >= 0:
                    self._device_combo.setCurrentIndex(idx)
        self._update_button_states()

    def _update_button_states(self) -> None:
        if not hasattr(self, "_stream_button"):
            return

        is_streaming = self._stream is not None
        has_devices = bool(self._device_combo.currentData())

        # Stream button is always enabled to alert if no emulator is connected
        self._stream_button.setEnabled(True)

        # Device combo is disabled while actively streaming or if no devices
        self._device_combo.setEnabled(has_devices and not is_streaming)

        # Pause is only enabled if currently streaming; disabled otherwise
        self._pause_button.setEnabled(is_streaming)

        # Clear button is enabled only if there are lines in the model
        self._clear_button.setEnabled(self._model.rowCount() > 0)

        # Export button is enabled only if there are visible lines to export
        self._export_button.setEnabled(self._proxy.rowCount() > 0)

    def _on_clear_clicked(self) -> None:
        self._model.clear()
        self._update_count()

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
        total = self._model.rowCount()
        visible = self._proxy.rowCount()
        if visible == total:
            self._count_label.setText(f"{total} lines")
        else:
            self._count_label.setText(f"{visible} / {total} lines")
        self._update_button_states()

    def _apply_filters(self) -> None:
        self._proxy.set_filters(
            self._level_combo.currentText(),
            self._tag_input.text(),
            self._pid_input.text(),
            self._regex_input.text(),
        )
        self._update_count()

    def _on_pause_toggled(self, checked: bool) -> None:
        self._model.set_paused(checked)
        if checked:
            self._pause_button.setText("Resume")
            self._pause_button.setIcon(get_icon("play", size=13, color=TEXT_MUTED))
        else:
            self._pause_button.setText("Pause")
            self._pause_button.setIcon(get_icon("pause", size=13, color=TEXT_MUTED))

    def _on_stream_toggled(self, checked: bool) -> None:
        if checked:
            serial = self._device_combo.currentData()
            if not serial:
                self._stream_button.setChecked(False)
                QMessageBox.warning(
                    self,
                    "No Emulator Connected",
                    "No Android device or emulator is currently connected.\n\n"
                    "Please connect an Android device via USB/Wi-Fi or start an emulator "
                    "to stream logcat.",
                )
                return

            self._stream_button.setText("Stop stream")
            self._stream_button.setIcon(get_icon("square", size=13, color="#ffffff"))

            self._stream = self._ctx.device_service._adb.logcat_stream(serial)
            self._stream.line_received.connect(self._model.queue)
            self._stream.finished.connect(self._on_stream_finished)
            self._stream.start()
        else:
            self._stream_button.setText("Start stream")
            self._stream_button.setIcon(get_icon("play", size=13, color="#ffffff"))
            if self._pause_button.isChecked():
                self._pause_button.setChecked(False)
            self._pause_button.setText("Pause")
            self._pause_button.setIcon(get_icon("pause", size=13, color=TEXT_MUTED))
            if self._stream:
                self._stream.stop()
                self._stream = None

        self._update_button_states()

    def _on_stream_finished(self) -> None:
        self._stream_button.setChecked(False)
        self._stream_button.setText("Start stream")
        self._stream_button.setIcon(get_icon("play", size=13, color="#ffffff"))
        if self._pause_button.isChecked():
            self._pause_button.setChecked(False)
        self._pause_button.setText("Pause")
        self._pause_button.setIcon(get_icon("pause", size=13, color=TEXT_MUTED))
        self._stream = None
        self._update_button_states()

    def export_view(self, destination: Path) -> int:
        """Export currently visible (filtered) log lines to a file.

        Supports .csv for structured export and .txt / .log for raw threadtime format.
        Returns the number of exported lines.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        count = self._proxy.rowCount()

        if destination.suffix.lower() == ".csv":
            with destination.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Time", "PID", "TID", "Level", "Tag", "Message"])
                for i in range(count):
                    source_idx = self._proxy.mapToSource(self._proxy.index(i, 0))
                    if not source_idx.isValid():
                        continue
                    line = self._model._rows[source_idx.row()]
                    writer.writerow(
                        [
                            line.timestamp,
                            line.pid,
                            line.tid,
                            line.priority,
                            line.tag,
                            line.message,
                        ]
                    )
        else:
            with destination.open("w", encoding="utf-8") as f:
                for i in range(count):
                    source_idx = self._proxy.mapToSource(self._proxy.index(i, 0))
                    if not source_idx.isValid():
                        continue
                    line = self._model._rows[source_idx.row()]
                    line_str = (
                        line.raw.rstrip()
                        if line.raw
                        else (
                            f"{line.timestamp} {line.pid:>5} {line.tid:>5} "
                            f"{line.priority} {line.tag}: {line.message}"
                        )
                    )
                    f.write(line_str + "\n")

        return count

    def _on_export_clicked(self) -> None:
        if self._proxy.rowCount() == 0:
            QMessageBox.information(
                self,
                "Export Logcat",
                "There are no log lines to export in the current view.",
            )
            return

        default_name = "logcat_export.txt"
        file_filter = "Text Files (*.txt);;Log Files (*.log);;CSV Files (*.csv);;All Files (*.*)"
        path_str, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Logcat View",
            default_name,
            file_filter,
        )
        if not path_str:
            return

        dest = Path(path_str)
        if not dest.suffix:
            if "csv" in selected_filter.lower():
                dest = dest.with_suffix(".csv")
            else:
                dest = dest.with_suffix(".txt")

        try:
            exported_count = self.export_view(dest)
            QMessageBox.information(
                self,
                "Export Successful",
                f"Successfully exported {exported_count} lines to:\n{dest.name}",
            )
        except OSError as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Could not export logcat view:\n{e}",
            )

    def select_device(self, serial: str) -> None:
        idx = self._device_combo.findData(serial)
        if idx >= 0:
            self._device_combo.setCurrentIndex(idx)
        self._update_button_states()
