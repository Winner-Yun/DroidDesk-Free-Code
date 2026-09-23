"""Reports page - Section 6.13. Unified report history table (combining build_record,
test_run, and scan from Repository) plus real export capabilities (HTML, PDF, JSON,
Markdown) rendered via ReportService.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.core.models import GateResult, ReleaseCheck
from droiddesk.core.severity import GateVerdict
from droiddesk.ui.theme import TEXT_MUTED, get_icon
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.status_pill import StatusPill

logger = logging.getLogger(__name__)

_VERDICT_STATUS = {
    "NO-GO": "fail",
    "GO": "pass",
    "PASS": "pass",
    "FAIL": "fail",
    "OVERRIDDEN": "warn",
    "WARN": "warn",
}


class ReportsPage(QWidget):
    upload_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._apk_path: Path | None = None
        self._history_items: list[dict[str, Any]] = []
        self.setProperty("role", "page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "Reports",
            "One template set. HTML is the source of truth; PDF and Markdown are "
            "rendered from it, and JSON comes straight off the domain model.",
        )
        folder_btn = QPushButton("Open output folder")
        folder_btn.setIcon(get_icon("folder-open", size=13, color=TEXT_MUTED))
        folder_btn.setIconSize(QSize(13, 13))
        folder_btn.clicked.connect(self._open_output_folder)
        header.add_action(folder_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(get_icon("rotate-cw", size=13, color=TEXT_MUTED))
        refresh_btn.setIconSize(QSize(13, 13))
        refresh_btn.clicked.connect(self.refresh_history)
        header.add_action(refresh_btn)
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
            title="No Active APK or Report History",
            message=(
                "Reports reflect test runs, gate verdicts, and security findings. "
                "Run a test, secret scan, or release gate to generate and export reports."
            ),
            button_text="Upload APK",
        )
        self._empty_state.upload_requested.connect(self.upload_requested.emit)
        outer.addWidget(self._empty_state, 1)

        self.refresh_history()

    def set_apk(self, path: Path | None) -> None:
        self._apk_path = path
        self.refresh_history()

    def refresh_history(self) -> None:
        """Reload report history from Repository combining build_record, test_run, and scan."""
        try:
            self._history_items = self._ctx.repository.list_report_history()
        except Exception as exc:
            logger.warning("Could not read report history: %s", exc)
            self._history_items = []

        has_data = len(self._history_items) > 0 or self._apk_path is not None
        if not has_data:
            self._content_container.hide()
            self._empty_state.show()
            return

        self._empty_state.hide()
        self._content_container.show()
        self._populate_table()

    def _build_history_panel(self) -> QWidget:
        card = Card("History")
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Report", "Kind", "Verdict", "When"])
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        card.body_layout().addWidget(self._table, 1)
        return card

    def _populate_table(self) -> None:
        self._table.setRowCount(len(self._history_items))
        for row, entry in enumerate(self._history_items):
            self._table.setItem(row, 0, QTableWidgetItem(str(entry.get("name", ""))))
            self._table.setItem(row, 1, QTableWidgetItem(str(entry.get("kind", ""))))

            verdict = str(entry.get("verdict", "UNKNOWN"))
            status = _VERDICT_STATUS.get(verdict, "info")
            if verdict in ("GO", "NO-GO", "PASS", "FAIL", "OVERRIDDEN", "WARN"):
                pill_widget = QWidget()
                pill_layout = QHBoxLayout(pill_widget)
                pill_layout.setContentsMargins(0, 0, 0, 0)
                pill_layout.addWidget(StatusPill(verdict, status))
                pill_layout.addStretch(1)
                self._table.setCellWidget(row, 2, pill_widget)
            else:
                self._table.setItem(row, 2, QTableWidgetItem(verdict))

            when_str = str(entry.get("when", ""))
            if "T" in when_str:
                when_str = when_str.replace("T", " ")[:19]
            when_item = QTableWidgetItem(when_str)
            when_item.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, 3, when_item)

        if self._history_items and self._table.currentRow() < 0:
            self._table.selectRow(0)

    def _build_export_panel(self) -> QWidget:
        card = Card("Export")

        exports = [
            ("HTML report", "html", "Standalone, self-contained single-file HTML report."),
            ("PDF report", "pdf", "Vector printable PDF formatted for distribution."),
            ("JSON export", "json", "Raw domain model serialized directly for pipeline ingestion."),
            ("Markdown report", "markdown", "Clean GitHub-flavored Markdown for PR summaries."),
        ]

        for label, fmt, caption in exports:
            btn = QPushButton(label)
            btn.setIcon(get_icon("file-down", size=13, color=TEXT_MUTED))
            btn.setIconSize(QSize(13, 13))
            btn.clicked.connect(lambda _checked=False, f=fmt: self._export_selected(f))
            card.body_layout().addWidget(btn)

            note = QLabel(caption)
            note.setWordWrap(True)
            note.setProperty("role", "muted")
            card.body_layout().addWidget(note)

        card.body_layout().addStretch(1)

        footer = QLabel(
            "Reports are generated strictly from the local SQLite repository and "
            "evaluated results without external telemetry."
        )
        footer.setWordWrap(True)
        footer.setProperty("role", "dim")
        card.body_layout().addWidget(footer)
        return card

    def _get_selected_entry(self) -> dict[str, Any] | None:
        row = self._table.currentRow()
        if 0 <= row < len(self._history_items):
            return self._history_items[row]
        if self._history_items:
            return self._history_items[0]
        return None

    def _export_selected(self, fmt: str) -> None:
        entry = self._get_selected_entry()
        if not entry:
            QMessageBox.information(
                self,
                "No Report Selected",
                "Please select an entry from the History table to export.",
            )
            return

        report_service = self._ctx.report_service
        if report_service is None:
            from droiddesk.services.report_service import ReportService

            report_service = ReportService()

        report_type = entry.get("report_type")
        raw_id = entry.get("raw_id")
        if raw_id is None:
            return
        raw_id_int = int(str(raw_id))
        rendered: str | bytes | None = None
        default_name = f"{report_type}_{raw_id}.{fmt if fmt != 'markdown' else 'md'}"

        try:
            if report_type == "test":
                run = self._ctx.repository.get_test_run(raw_id_int)
                if not run:
                    QMessageBox.warning(self, "Export Error", f"Test run #{raw_id} not found.")
                    return
                rendered = report_service.render_test_report(run, fmt)  # type: ignore[arg-type]

            elif report_type == "scan":
                scan = self._ctx.repository.get_scan(raw_id_int)
                if not scan:
                    QMessageBox.warning(self, "Export Error", f"Scan #{raw_id} not found.")
                    return
                rendered = report_service.render_scan_report(scan, fmt)  # type: ignore[arg-type]

            elif report_type == "gate":
                record = self._ctx.repository.get_build_record(raw_id_int)
                if not record:
                    QMessageBox.warning(self, "Export Error", f"Gate record #{raw_id} not found.")
                    return
                verdict_val = record.gate_verdict or "GO"
                try:
                    gate_verdict = GateVerdict(verdict_val)
                except ValueError:
                    gate_verdict = GateVerdict.GO

                gate_result = GateResult(
                    checks=[
                        ReleaseCheck("Environment", True, 20, True, record.environment),
                        ReleaseCheck(
                            "Command Execution",
                            record.exit_code == 0 if record.exit_code is not None else True,
                            40,
                            True,
                            record.command,
                        ),
                    ],
                    score=record.gate_score or 100,
                    verdict=gate_verdict,
                    override_note=record.override_note,
                )
                rendered = report_service.render_gate_report(gate_result, fmt)  # type: ignore[arg-type]

        except Exception as exc:
            logger.error("Failed to render report: %s", exc)
            QMessageBox.critical(self, "Export Failed", f"Could not render report: {exc}")
            return

        if rendered is None:
            return

        out_dir = self._ctx.settings.data_dir / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        init_path = str(out_dir / default_name)

        ext_filter = f"{fmt.upper()} Files (*.{fmt if fmt != 'markdown' else 'md'});;All Files (*)"
        save_path, _ = QFileDialog.getSaveFileName(
            self, f"Export {fmt.upper()} Report", init_path, ext_filter
        )
        if not save_path:
            return

        try:
            target = Path(save_path)
            if isinstance(rendered, bytes):
                target.write_bytes(rendered)
            else:
                target.write_text(rendered, encoding="utf-8")
            QMessageBox.information(
                self, "Export Complete", f"Report saved successfully to:\n{target.name}"
            )
        except OSError as exc:
            QMessageBox.critical(self, "Save Error", f"Could not write file: {exc}")

    def _open_output_folder(self) -> None:
        out_dir = self._ctx.settings.data_dir / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))
