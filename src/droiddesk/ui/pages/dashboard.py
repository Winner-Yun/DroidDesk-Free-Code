"""Dashboard page. Aggregates data from every other feature (Section 9); this
pass renders it against `ui.static_data` so the layout is proven out before
each source page goes live and the aggregation gets wired for real.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from droiddesk.ui import static_data
from droiddesk.ui.widgets.card import Card, PageHeader, StatCard
from droiddesk.ui.widgets.status_pill import StatusPill

_SEVERITY_LABELS = {"critical": "CRITICAL", "high": "HIGH", "review": "NEEDS REVIEW"}
_SEVERITY_COLORS = {"critical": "#c0392b", "high": "#e67e22", "review": "#f1c40f"}


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alpha})"


class DashboardPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        header = PageHeader("Dashboard", "Current project state, and the last thing that happened in it.")
        header.add_action(QPushButton("⛁  Switch project"))
        run_gate_button = QPushButton("Run release gate")
        run_gate_button.setProperty("role", "primary")
        header.add_action(run_gate_button)
        outer.addWidget(header)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)
        for stat in static_data.DASHBOARD_STATS:
            stats_row.addWidget(StatCard(stat.value, stat.label))
        outer.addLayout(stats_row)

        panels_row = QHBoxLayout()
        panels_row.setSpacing(14)
        panels_row.addWidget(self._build_needs_attention(), 1)
        panels_row.addWidget(self._build_recent_runs(), 1)
        outer.addLayout(panels_row, 1)

    def _build_needs_attention(self) -> QWidget:
        card = Card("Needs attention")
        subtitle = QLabel("Sorted by severity, not by when it was found.")
        subtitle.setProperty("role", "muted")
        card.body_layout().addWidget(subtitle)

        for item in static_data.NEEDS_ATTENTION:
            row = QWidget()
            row.setStyleSheet(f"background: {_rgba(_SEVERITY_COLORS[item.severity], 0.08)}; border-radius: 6px;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 8, 10, 8)
            row_layout.setSpacing(12)

            badge = QLabel(_SEVERITY_LABELS[item.severity])
            color = _SEVERITY_COLORS[item.severity]
            badge.setStyleSheet(
                f"background: transparent; color: {color}; border: 1px solid {color}; "
                f"border-radius: 3px; padding: 2px 6px; font-size: 10px; font-weight: 700;"
            )
            row_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            title = QLabel(item.title)
            title.setStyleSheet("font-weight: 600; font-size: 12px;")
            location = QLabel(item.location)
            location.setProperty("role", "mono")
            text_col.addWidget(title)
            text_col.addWidget(location)
            row_layout.addLayout(text_col, 1)

            card.body_layout().addWidget(row)

        card.body_layout().addStretch(1)
        return card

    def _build_recent_runs(self) -> QWidget:
        card = Card("Recent runs")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        for row, run in enumerate(static_data.RECENT_RUNS):
            grid.addWidget(StatusPill(run.status, run.status), row, 0)
            title = QLabel(run.title)
            grid.addWidget(title, row, 1)
            when = QLabel(run.when)
            when.setProperty("role", "muted")
            when.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(when, row, 2)
        grid.setColumnStretch(1, 1)
        card.body_layout().addLayout(grid)
        card.body_layout().addStretch(1)
        return card
