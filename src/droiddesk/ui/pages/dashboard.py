"""Dashboard page. Built last (Phase 6, Section 9) — it aggregates data from every
other feature, so building it before those features exist means rebuilding it
three times.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Dashboard — populated in Phase 6"))
