"""Reports page — Section 6.13. Test run / scan / gate report history with
HTML/PDF/JSON/Markdown export.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ReportsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Reports — Phase 3+"))
        # TODO: list backed by Repository, export buttons calling ReportService.
