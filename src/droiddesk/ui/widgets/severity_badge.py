"""Colour-coded severity badge — the visual half of "classify, do not alarm"
(Section 1.3). Critical/high/review/info must read as distinct at a glance.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from droiddesk.core.severity import Severity

_COLORS = {
    Severity.CRITICAL: "#c0392b",
    Severity.HIGH: "#e67e22",
    Severity.NEEDS_REVIEW: "#f1c40f",
    Severity.INFORMATIONAL: "#7f8c8d",
}


class SeverityBadge(QLabel):
    def __init__(self, severity: Severity) -> None:
        super().__init__(severity.value.upper())
        color = _COLORS[severity]
        self.setStyleSheet(
            f"background: {color}; color: white; border-radius: 3px; "
            f"padding: 2px 6px; font-weight: 600; font-size: 11px;"
        )
