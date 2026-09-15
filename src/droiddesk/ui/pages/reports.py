"""Reports page — Section 6.13. Report history table plus the export panel
(HTML/PDF/JSON/Markdown). Populated from `static_data.REPORT_HISTORY`; the
export buttons call `ReportService` once it exists (Phase 3+), rendering
through the same Jinja2 template set referenced in `reports/renderer.py`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.ui import static_data
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.status_pill import StatusPill

_VERDICT_STATUS = {"NO-GO": "fail", "GO": "pass", "PASS": "pass", "FAIL": "fail"}


class ReportsPage(QWidget):
    upload_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._apk_path: Path | None = None
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "Reports",
            "One template set. HTML is the source of truth; PDF and Markdown are "
            "rendered from it, and JSON comes straight off the domain model.",
        )
        header.add_action(QPushButton("⛁  Open output folder"))
        outer.addWidget(header)

        self._content_container = QWidget()
        content_layout = QVBoxLayout(self._content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)
        content_row.addWidget(self._build_history_panel(), 2)
        content_row.addWidget(self._build_export_panel(), 1)
        content_layout.addLayout(content_row)
        outer.addWidget(self._content_container, 1)

        self._empty_state = EmptyStateWidget(
            title="No Active APK Selected",
            message=(
                "Reports reflect test runs, gate verdicts, and security findings for "
                "an APK. Select or upload an APK to generate and export reports."
            ),
            button_text="Upload APK",
        )
        self._empty_state.upload_requested.connect(self.upload_requested.emit)
        outer.addWidget(self._empty_state, 1)

        self.set_apk(None)

    def set_apk(self, path: Path | None) -> None:
        self._apk_path = path
        if path is None:
            self._content_container.hide()
            self._empty_state.show()
        else:
            self._empty_state.hide()
            self._content_container.show()

    def _build_history_panel(self) -> QWidget:
        card = Card("History")
        table = QTableWidget(len(static_data.REPORT_HISTORY), 4)
        table.setHorizontalHeaderLabels(["Report", "Kind", "Verdict", "When"])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for row, entry in enumerate(static_data.REPORT_HISTORY):
            table.setItem(row, 0, QTableWidgetItem(entry.name))
            table.setItem(row, 1, QTableWidgetItem(entry.kind))
            status = _VERDICT_STATUS.get(entry.verdict, "info")
            if entry.verdict in ("GO", "NO-GO", "PASS", "FAIL"):
                pill_widget = QWidget()
                pill_layout = QHBoxLayout(pill_widget)
                pill_layout.setContentsMargins(0, 0, 0, 0)
                pill_layout.addWidget(StatusPill(entry.verdict, status))
                pill_layout.addStretch(1)
                table.setCellWidget(row, 2, pill_widget)
            else:
                table.setItem(row, 2, QTableWidgetItem(entry.verdict))
            when_item = QTableWidgetItem(entry.when)
            when_item.setForeground(Qt.GlobalColor.gray)
            table.setItem(row, 3, when_item)

        card.body_layout().addWidget(table, 1)
        return card

    def _build_export_panel(self) -> QWidget:
        card = Card("Export")
        for label, caption in static_data.REPORT_EXPORTS:
            button = QPushButton(label)
            card.body_layout().addWidget(button)
            note = QLabel(caption)
            note.setWordWrap(True)
            note.setProperty("role", "muted")
            card.body_layout().addWidget(note)

        card.body_layout().addStretch(1)

        footer = QLabel(static_data.REPORT_FOOTER_NOTE)
        footer.setWordWrap(True)
        footer.setProperty("role", "dim")
        card.body_layout().addWidget(footer)
        return card

    # TODO: bind the history table to Repository; wire export buttons to
    # ReportService once it exists.
