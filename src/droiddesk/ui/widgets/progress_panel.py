"""Cancellable progress indicator for long-running work (scans, hashing, test
runs). Design principle: never block the interface, and every long task must be
cancellable (Section 1.3, Section 4.2).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget


class ProgressPanel(QWidget):
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        self._label = QLabel("")
        self._bar = QProgressBar()
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self.cancel_requested)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)
        layout.addWidget(self._cancel_button)
        self.hide()

    def start(self, label: str, total: int) -> None:
        self._label.setText(label)
        self._bar.setRange(0, total)
        self._bar.setValue(0)
        self.show()

    def update_progress(self, current: int, total: int) -> None:
        self._bar.setRange(0, total)
        self._bar.setValue(current)

    def finish(self) -> None:
        self.hide()
