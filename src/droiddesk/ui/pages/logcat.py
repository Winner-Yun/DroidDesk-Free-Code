"""Logcat page — Section 6.4. LogcatModel-backed table view with a
QSortFilterProxyModel over tag/priority/PID/regex, pause control, and filtered
export.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from droiddesk.ui.models.logcat_model import LogcatModel


class LogcatPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._model = LogcatModel()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Logcat — Phase 2"))
        # TODO(Phase 2): QTableView bound to self._model via a
        # QSortFilterProxyModel; pause control stops appending without killing
        # the underlying AdbStream.
