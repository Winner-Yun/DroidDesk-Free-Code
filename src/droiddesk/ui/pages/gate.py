"""Release Gate page — Section 6.10. A single verdict panel (score + GO/NO-GO)
next to the dependency-ordered checks list. A separate sidebar entry and page
from Build Commands in the mockups, even though both are driven by
`GateService` in the spec. Populated from `static_data.GATE_CHECKS`; Phase 5
swaps in `GateService.evaluate()` without changing this layout.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from droiddesk.context import AppContext
from droiddesk.ui import static_data
from droiddesk.ui.theme import STATUS_COLORS
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.status_pill import StatusIcon, TagPill


class _ScoreDial(QWidget):
    """Circular score ring with the score and verdict text overlaid at its
    centre — a QWidget can paint its own background and still lay out child
    labels on top of it.
    """

    def __init__(self, score: int, verdict: str, color: str) -> None:
        super().__init__()
        self._score = score
        self._color = color
        self.setFixedSize(160, 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        score_label = QLabel(str(score))
        score_label.setStyleSheet("font-size: 34px; font-weight: 800; background: transparent;")
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        verdict_label = QLabel(verdict)
        verdict_label.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 800; "
            "letter-spacing: 1px; background: transparent;"
        )
        verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(score_label)
        layout.addWidget(verdict_label)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)

        track_pen = QPen(Qt.GlobalColor.darkGray)
        track_pen.setWidth(8)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

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
        self._apk_path: Path | None = None
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "Release gate",
            "Every check at once, one verdict. A clean result means no issues "
            "were found by the checks performed — not that the build is secure.",
        )
        header.add_action(QPushButton("↓  Export gate report"))
        run_button = QPushButton("Run gate")
        run_button.setProperty("role", "primary")
        header.add_action(run_button)
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

        verdict_color = (
            STATUS_COLORS["fail"] if static_data.GATE_VERDICT == "NO-GO" else STATUS_COLORS["pass"]
        )

        dial = _ScoreDial(static_data.GATE_SCORE, static_data.GATE_VERDICT, verdict_color)
        layout.addWidget(dial, 0, Qt.AlignmentFlag.AlignCenter)

        blocked = QLabel(static_data.GATE_BLOCKED_REASON)
        blocked.setStyleSheet("font-weight: 700; font-size: 14px;")
        blocked.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(blocked)

        note = QLabel(static_data.GATE_SCORE_NOTE)
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)

        override_button = QPushButton("Override and build anyway")
        override_button.setProperty("role", "outlineRed")
        layout.addWidget(override_button)

        layout.addStretch(1)
        return card

    def _build_checks_panel(self) -> QWidget:
        card = Card("Checks")
        note = QLabel("Evaluated in dependency order; a hard failure short-circuits the rest.")
        note.setProperty("role", "muted")
        card.body_layout().addWidget(note)

        for check in static_data.GATE_CHECKS:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(StatusIcon(check.status))

            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            name = QLabel(check.name)
            name.setStyleSheet("font-weight: 600;")
            detail = QLabel(check.detail)
            detail.setWordWrap(True)
            detail.setProperty("role", "muted")
            text_col.addWidget(name)
            text_col.addWidget(detail)
            row.addLayout(text_col, 1)

            if check.blocking:
                row.addWidget(TagPill("blocking"))
            weight = QLabel(str(check.weight))
            weight.setProperty("role", "muted")
            weight.setFixedWidth(24)
            weight.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(weight)

            card.body_layout().addLayout(row)

        footer = QLabel(static_data.GATE_FOOTER_NOTE)
        footer.setWordWrap(True)
        footer.setProperty("role", "dim")
        footer.setStyleSheet(footer.styleSheet() + " margin-top: 10px;")
        card.body_layout().addWidget(footer)

        card.body_layout().addStretch(1)
        return card

    # TODO(Phase 5): bind to GateResult from GateService.evaluate(); wire
    # Override and build anyway to GateService.override() with a typed reason.
