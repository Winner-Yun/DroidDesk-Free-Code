"""Real-time Device Logcat Viewer dialog."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import override

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.infra.adb import AdbClient
from droiddesk.infra.process import AdbStream
from droiddesk.ui.theme import get_icon

_LEVEL_MAP = {
    "All Levels": "",
    "Verbose (V)": " V ",
    "Debug (D)": " D ",
    "Info (I)": " I ",
    "Warning (W)": " W ",
    "Error (E)": " E ",
}


class DeviceLogsDialog(QDialog):
    """Dedicated live logcat streaming dialog for any active device."""

    def __init__(
        self,
        serial: str,
        device_name: str,
        adb_client: AdbClient,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._serial = serial
        self._device_name = device_name
        self._adb = adb_client
        self._stream: AdbStream | None = None
        self._all_lines: list[str] = []
        self._is_paused = False

        self.setWindowTitle(f"Device Logs - {device_name} ({serial})")
        self.resize(880, 560)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1a1b1e;
                color: #e5e7eb;
            }
            QLabel {
                color: #e5e7eb;
            }
            QLineEdit, QComboBox {
                background-color: #212226;
                color: #ffffff;
                border: 1px solid #35373e;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 12px;
            }
            QPlainTextEdit {
                background-color: #111215;
                color: #d1d5db;
                border: 1px solid #2a2c31;
                border-radius: 4px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
                line-height: 1.4;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # Pause / Resume Button
        self._pause_btn = QPushButton("Pause Stream")
        self._pause_btn.setIcon(get_icon("pause", size=12, color="#9ca3af"))
        self._pause_btn.clicked.connect(self._toggle_pause)
        toolbar.addWidget(self._pause_btn)

        # Clear Button
        clear_btn = QPushButton("Clear")
        clear_btn.setIcon(get_icon("trash-2", size=12, color="#9ca3af"))
        clear_btn.clicked.connect(self._clear_logs)
        toolbar.addWidget(clear_btn)

        # Level Filter
        self._level_combo = QComboBox()
        for lvl in _LEVEL_MAP:
            self._level_combo.addItem(lvl)
        self._level_combo.currentTextChanged.connect(self._apply_filter)
        toolbar.addWidget(self._level_combo)

        # Text Filter
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Filter logs (regex or text)...")
        self._filter_input.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self._filter_input, 1)

        # Auto-scroll Checkbox
        self._auto_scroll_cb = QCheckBox("Auto-scroll")
        self._auto_scroll_cb.setChecked(True)
        toolbar.addWidget(self._auto_scroll_cb)

        # Export Button
        export_btn = QPushButton("Export...")
        export_btn.setIcon(get_icon("download", size=12, color="#9ca3af"))
        export_btn.clicked.connect(self._export_logs)
        toolbar.addWidget(export_btn)

        layout.addLayout(toolbar)

        # Log Text Box
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(10000)
        layout.addWidget(self._log_view, 1)

        # Status Bar Footer
        footer = QHBoxLayout()
        self._count_lbl = QLabel("0 log entries")
        self._count_lbl.setStyleSheet("font-size: 11px; color: #8b8e94;")
        footer.addWidget(self._count_lbl)
        footer.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

        self._start_stream()

    def _start_stream(self) -> None:
        try:
            self._stream = self._adb.logcat_stream(self._serial)
            self._stream.line_received.connect(self._on_log_line)
            self._stream.start()
        except Exception as exc:
            self._log_view.appendPlainText(f"Failed to start logcat stream: {exc}")

    def _on_log_line(self, line: str) -> None:
        self._all_lines.append(line)
        self._count_lbl.setText(f"{len(self._all_lines)} log entries")

        if self._is_paused:
            return

        if self._matches_filter(line):
            self._log_view.appendPlainText(line)
            if self._auto_scroll_cb.isChecked():
                self._log_view.verticalScrollBar().setValue(
                    self._log_view.verticalScrollBar().maximum()
                )

    def _matches_filter(self, line: str) -> bool:
        lvl_key = self._level_combo.currentText()
        lvl_marker = _LEVEL_MAP.get(lvl_key, "")
        if lvl_marker and lvl_marker not in line:
            return False

        q = self._filter_input.text().strip().lower()
        return not (q and q not in line.lower())

    def _apply_filter(self) -> None:
        self._log_view.clear()
        matching = [entry for entry in self._all_lines if self._matches_filter(entry)]
        self._log_view.setPlainText("\n".join(matching))
        if self._auto_scroll_cb.isChecked():
            self._log_view.verticalScrollBar().setValue(
                self._log_view.verticalScrollBar().maximum()
            )

    def _toggle_pause(self) -> None:
        self._is_paused = not self._is_paused
        if self._is_paused:
            self._pause_btn.setText("Resume Stream")
            self._pause_btn.setIcon(get_icon("play", size=12, color="#10b981"))
        else:
            self._pause_btn.setText("Pause Stream")
            self._pause_btn.setIcon(get_icon("pause", size=12, color="#9ca3af"))
            self._apply_filter()

    def _clear_logs(self) -> None:
        self._all_lines.clear()
        self._log_view.clear()
        self._count_lbl.setText("0 log entries")
        with contextlib.suppress(Exception):
            self._adb.logcat_clear(self._serial)

    def _export_logs(self) -> None:
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Logcat",
            f"logcat_{self._serial}.log",
            "Log Files (*.log *.txt);;All Files (*)",
        )
        if save_path:
            try:
                Path(save_path).write_text("\n".join(self._all_lines), encoding="utf-8")
                QMessageBox.information(
                    self, "Logs Exported", f"Successfully saved to:\n{save_path}"
                )
            except Exception as exc:
                QMessageBox.warning(self, "Export Failed", f"Could not export logs:\n{exc}")

    @override
    def closeEvent(self, event) -> None:
        if self._stream:
            self._stream.stop()
        super().closeEvent(event)
