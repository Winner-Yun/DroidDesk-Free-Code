"""Small colour-coded indicators shared across pages: filled status pills
(PASS/FAIL/WARN/GO/NO-GO), the pass/warn/fail check-mark used in guard and
gate checklists, and the small dot used for device connection state. Kept
separate from `severity_badge.py` because severity (critical/high/review/info)
and run status (pass/warn/fail) are different axes that happen to reuse the
same colour vocabulary.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from droiddesk.ui.theme import STATUS_COLORS, get_pixmap

_LUCIDE_STATUS_ICONS = {"pass": "circle-check", "warn": "triangle-alert", "fail": "circle-x"}


class StatusPill(QLabel):
    """Filled rounded-rect badge, e.g. PASS / FAIL / WARN / GO / NO-GO."""

    def __init__(self, text: str, status: str) -> None:
        super().__init__(text.upper())
        self.set_status(text, status)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_status(self, text: str, status: str) -> None:
        self.setText(text.upper())
        color = STATUS_COLORS.get(status, STATUS_COLORS["info"])
        self.setStyleSheet(
            f"background: {color}; color: white; border-radius: 3px; "
            f"padding: 2px 8px; font-weight: 700; font-size: 11px;"
        )


class StatusIcon(QLabel):
    """Vector check/warning/cross icon used at the start of a guard/gate row."""

    def __init__(self, status: str) -> None:
        super().__init__()
        self.setFixedSize(18, 18)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        icon_name = _LUCIDE_STATUS_ICONS.get(status, "circle-help")
        color = STATUS_COLORS.get(status, STATUS_COLORS.get("info", "#888888"))
        pix = get_pixmap(icon_name, size=16, color=color)
        self.setPixmap(pix)


class StatusDot(QLabel):
    """Small filled circle used for device connection state."""

    def __init__(self, status: str) -> None:
        super().__init__()
        from droiddesk.ui.theme import is_light

        ready_color = "#9ca3af" if is_light() else "#c7c9cc"
        colors = {
            "ready": ready_color,
            "active": STATUS_COLORS["pass"],
            "unauthorized": STATUS_COLORS["warn"],
            "offline": STATUS_COLORS["fail"],
        }
        color = colors.get(status, "#6b7280" if is_light() else "#5c5f66")
        self.setFixedSize(9, 9)
        self.setStyleSheet(f"background: {color}; border-radius: 4px;")


class TagPill(QLabel):
    """Neutral outlined pill, e.g. the "blocking" tag on a guard row."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setProperty("role", "tagPill")
