"""Security page — Section 6.5/6.6/6.7. Findings view (severity-grouped, redacted
previews, suppression workflow), Privacy Scanner results, and the Permission
Analyzer.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from droiddesk.ui.models.findings_model import FindingsModel


class SecurityPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._model = FindingsModel()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Security — Phase 4"))
        # TODO(Phase 4): QTableView bound to self._model, grouped by Severity,
        # with a suppress action writing to .droiddesk/suppressions.toml.
