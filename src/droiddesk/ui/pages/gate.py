"""Release Gate page — Section 6.10. A single verdict panel (score + GO/NO-GO)
next to the dependency-ordered checks list.

Phase 5 connects GateService:
- evaluate_async() runs release checks in dependency order on QThreadPool.
- Live score dial and checks list update upon evaluation.
- OverrideDialog prompts for an audit reason to bypass blocking checks.
- CRITICAL secret findings are hard-blocked and cannot be bypassed.
- Export report action saves structured JSON audit summary.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.core.models import GateResult
from droiddesk.core.severity import GateVerdict
from droiddesk.ui.dialogs.override_dialog import OverrideDialog
from droiddesk.ui.theme import STATUS_COLORS, TEXT_MUTED, get_icon
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.status_pill import StatusIcon, TagPill


class _ScoreDial(QWidget):
    """Circular score ring with the score and verdict text overlaid at centre."""

    def __init__(self, score: int, verdict: str, color: str) -> None:
        super().__init__()
        self._score = score
        self._verdict = verdict
        self._color = color
        self.setFixedSize(160, 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._score_label = QLabel(str(score))
        self._score_label.setStyleSheet(
            "font-size: 34px; font-weight: 800; background: transparent; color: #f4f4f5;"
        )
        self._score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._verdict_label = QLabel(verdict)
        self._verdict_label.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 800; "
            "letter-spacing: 1px; background: transparent;"
        )
        self._verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self._score_label)
        layout.addWidget(self._verdict_label)

    def set_score(self, score: int, verdict: str, color: str) -> None:
        self._score = max(0, min(100, score))
        self._verdict = verdict
        self._color = color
        self._score_label.setText(str(self._score))
        self._verdict_label.setText(verdict)
        self._verdict_label.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 800; "
            "letter-spacing: 1px; background: transparent;"
        )
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)

        track_pen = QPen(QColor("#2a2c33"))
        track_pen.setWidth(8)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        if self._score > 0:
            score_pen = QPen(QColor(self._color))
            score_pen.setWidth(8)
            score_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(score_pen)
            span = int(360 * 16 * (self._score / 100))
            painter.drawArc(rect, 90 * 16, -span)

        painter.end()
        super().paintEvent(event)


class GatePage(QWidget):
    upload_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._gate_service = ctx.gate_service
        self._env_service = ctx.env_service
        self._apk_path: Path | None = None
        self._current_result: GateResult | None = None

        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "Release gate",
            "Every check at once, one verdict. A clean result means no issues "
            "were found by the checks performed — not that the build is secure.",
        )
        export_btn = QPushButton("Export gate report")
        export_btn.setIcon(get_icon("file-down", size=14, color=TEXT_MUTED))
        export_btn.setIconSize(QSize(14, 14))
        export_btn.clicked.connect(self._on_export_report)
        header.add_action(export_btn)

        self._run_button = QPushButton("Run gate")
        self._run_button.setProperty("role", "primary")
        self._run_button.setIcon(get_icon("shield-check", size=14, color="#ffffff"))
        self._run_button.setIconSize(QSize(14, 14))
        self._run_button.clicked.connect(self._on_run_gate)
        header.add_action(self._run_button)
        outer.addWidget(header)

        self._content_container = QWidget()
        content_layout = QVBoxLayout(self._content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        columns.addWidget(self._build_verdict_panel(), 1)
        columns.addWidget(self._build_checks_panel(), 2)
        content_layout.addLayout(columns)
        outer.addWidget(self._content_container, 1)

        self._empty_state = EmptyStateWidget(
            title="No APK Selected for Release Gate",
            message=(
                "The release gate evaluates signatures, privacy, permissions, and "
                "bundle size. Select an APK from the app bar or upload one to evaluate."
            ),
            button_text="Upload APK",
        )
        self._empty_state.upload_requested.connect(self.upload_requested.emit)
        outer.addWidget(self._empty_state, 1)

        if self._gate_service:
            self._gate_service.gate_evaluated.connect(self._on_gate_evaluated)
            self._gate_service.gate_failed.connect(self._on_gate_failed)

        self.set_apk(None)

    def set_apk(self, path: Path | None) -> None:
        self._apk_path = path
        if path is None:
            self._content_container.hide()
            self._empty_state.show()
        else:
            self._empty_state.hide()
            self._content_container.show()

    def _build_verdict_panel(self) -> QWidget:
        card = Card()
        layout = card.body_layout()
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._score_dial = _ScoreDial(0, "—", "#6b7280")
        layout.addWidget(self._score_dial, 0, Qt.AlignmentFlag.AlignCenter)

        self._blocked_label = QLabel("Awaiting Release Gate Run")
        self._blocked_label.setStyleSheet("font-weight: 700; font-size: 14px; color: #9ca3af;")
        self._blocked_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._blocked_label)

        self._score_note = QLabel(
            "The score tracks improvement over time. The verdict governs the build. "
            "Click 'Run gate' above to evaluate."
        )
        self._score_note.setWordWrap(True)
        self._score_note.setProperty("role", "muted")
        self._score_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._score_note)

        self._override_button = QPushButton("Override and build anyway")
        self._override_button.setProperty("role", "outlineRed")
        self._override_button.setEnabled(False)
        self._override_button.clicked.connect(self._on_override_clicked)
        layout.addWidget(self._override_button)

        layout.addStretch(1)
        return card

    def _build_checks_panel(self) -> QWidget:
        self._checks_card = Card("Checks")
        note = QLabel("Evaluated in dependency order; a hard failure short-circuits the rest.")
        note.setProperty("role", "muted")
        self._checks_card.body_layout().addWidget(note)

        self._checks_container = QWidget()
        self._checks_layout = QVBoxLayout(self._checks_container)
        self._checks_layout.setContentsMargins(0, 0, 0, 0)
        self._checks_layout.setSpacing(8)

        # Initial predefined categories
        initial_categories = (
            ("project_identifier", True, 10, "Package name matches expected release identifier"),
            ("environment", True, 20, "Production active and permitted to build releases"),
            ("git_clean", False, 10, "Working tree clean, on a release branch"),
            ("secrets", True, 20, "No critical findings in the project tree"),
            ("apk_valid_signed", True, 15, "Valid, signed with v2 or later, correct target SDK"),
            ("privacy", True, 15, "No credential files present inside the APK"),
            ("permissions", False, 5, "No unreviewed high-risk permissions"),
            ("size", False, 5, "Under the configured threshold (60 MB)"),
        )
        for name, blocking, weight, detail in initial_categories:
            self._add_check_row(
                category=name,
                passed=False,
                blocking=blocking,
                weight=weight,
                detail=detail,
                status="pending",
            )

        self._checks_card.body_layout().addWidget(self._checks_container)

        footer = QLabel(
            "DroidDesk performs automated checks for commonly misplaced configuration "
            "and credential files. All findings should be assessed by a person "
            "before acting on them."
        )
        footer.setWordWrap(True)
        footer.setProperty("role", "dim")
        footer.setStyleSheet(footer.styleSheet() + " margin-top: 10px;")
        self._checks_card.body_layout().addWidget(footer)
        self._checks_card.body_layout().addStretch(1)

        return self._checks_card

    def _add_check_row(
        self,
        category: str,
        passed: bool,
        blocking: bool,
        weight: int,
        detail: str,
        status: str | None = None,
    ) -> None:
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(10)

        if status is not None:
            status_key = status
        else:
            status_key = "pass" if passed else ("fail" if blocking else "warn")
        icon = StatusIcon(status_key)
        row.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        name = QLabel(category)
        name.setStyleSheet("font-weight: 600; font-size: 12px; color: #f4f4f5;")
        detail_lbl = QLabel(detail)
        detail_lbl.setWordWrap(True)
        detail_lbl.setProperty("role", "muted")
        text_col.addWidget(name)
        text_col.addWidget(detail_lbl)
        row.addLayout(text_col, 1)

        if blocking:
            row.addWidget(TagPill("blocking"))

        wt_lbl = QLabel(str(weight))
        wt_lbl.setProperty("role", "muted")
        wt_lbl.setFixedWidth(24)
        wt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(wt_lbl)

        self._checks_layout.addWidget(row_widget)

    def _on_run_gate(self) -> None:
        if not self._gate_service or not self._apk_path:
            return

        project_root = self._env_service.project_root if self._env_service else Path.cwd()

        self._run_button.setEnabled(False)
        self._run_button.setText("Evaluating...")
        self._gate_service.evaluate_async(project_root, self._apk_path)

    def _on_gate_evaluated(self, result: GateResult) -> None:
        self._current_result = result
        self._run_button.setEnabled(True)
        self._run_button.setText("Run gate")

        # Determine verdict display
        if result.verdict == GateVerdict.GO:
            verdict_text = "GO"
            verdict_color = STATUS_COLORS["pass"]
            self._blocked_label.setText("All checks passed")
            self._blocked_label.setStyleSheet("font-weight: 700; font-size: 14px; color: #4ec994;")
            self._override_button.setEnabled(False)
        elif result.verdict == GateVerdict.OVERRIDDEN:
            verdict_text = "OVERRIDDEN"
            verdict_color = "#e5c07b"
            note = f"Overridden: {result.override_note}" if result.override_note else "Overridden"
            self._blocked_label.setText(note)
            self._blocked_label.setStyleSheet("font-weight: 700; font-size: 14px; color: #e5c07b;")
            self._override_button.setEnabled(False)
        else:
            verdict_text = "NO-GO"
            verdict_color = STATUS_COLORS["fail"]
            first_blocking = next((c for c in result.checks if c.blocking and not c.passed), None)
            if first_blocking:
                self._blocked_label.setText(f"Blocked on {first_blocking.category}")
            else:
                self._blocked_label.setText("Gate blocked")
            self._blocked_label.setStyleSheet("font-weight: 700; font-size: 14px; color: #f43f5e;")
            self._override_button.setEnabled(True)

        self._score_dial.set_score(result.score, verdict_text, verdict_color)

        # Clear and rebuild check rows
        while self._checks_layout.count():
            item = self._checks_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

        for c in result.checks:
            self._add_check_row(
                category=c.category,
                passed=c.passed,
                blocking=c.blocking,
                weight=c.weight,
                detail=c.detail,
            )

    def _on_gate_failed(self, error: str) -> None:
        self._run_button.setEnabled(True)
        self._run_button.setText("Run gate")
        QMessageBox.warning(
            self,
            "Gate Evaluation Error",
            f"Failed to evaluate release gate: {error}",
        )

    def _on_override_clicked(self) -> None:
        if not self._current_result or not self._gate_service:
            return

        # Check for critical secrets hard-block
        has_secret_fail = any(
            c.category == "secrets" and not c.passed for c in self._current_result.checks
        )
        if has_secret_fail:
            QMessageBox.critical(
                self,
                "Override Hard-Blocked",
                "CRITICAL secret findings were detected.\n"
                "The release gate strictly blocks releases with critical secrets "
                "and cannot be overridden.",
            )
            return

        blocking_fails = [c for c in self._current_result.checks if c.blocking and not c.passed]
        if not blocking_fails:
            return

        failed_descs = [f"{c.category}: {c.detail}" for c in blocking_fails]
        dialog = OverrideDialog(failed_descs, title="Override Release Gate", parent=self)
        if dialog.exec() == OverrideDialog.DialogCode.Accepted:
            reason = dialog.reason()
            new_result = self._gate_service.override(self._current_result, reason)
            self._on_gate_evaluated(new_result)

    def _on_export_report(self) -> None:
        if not self._current_result:
            QMessageBox.information(
                self,
                "Export Gate Report",
                "No gate evaluation has been performed yet.",
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Gate Report",
            "release-gate-report.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        report_data = {
            "score": self._current_result.score,
            "verdict": self._current_result.verdict.value,
            "override_note": self._current_result.override_note,
            "apk_path": str(self._apk_path) if self._apk_path else None,
            "checks": [
                {
                    "category": c.category,
                    "passed": c.passed,
                    "blocking": c.blocking,
                    "weight": c.weight,
                    "detail": c.detail,
                }
                for c in self._current_result.checks
            ],
        }

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2)
            QMessageBox.information(
                self,
                "Report Exported",
                f"Successfully exported gate report to:\n{file_path}",
            )
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", f"Failed to save report: {e}")
