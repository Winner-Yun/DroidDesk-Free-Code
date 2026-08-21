"""Application shell navigation — Section 5. A grouped, badge-aware sidebar
(Overview / Connect / Inspect / Protect / Ship, with Settings pinned to the
bottom) replaces the flat `QListWidget` the scaffold started with, matching
the approved mockups.

No icon assets are bundled yet (`resources/icons/` is empty — see
`resources/README.md`), so nav rows use plain Unicode glyphs as stand-ins
rather than pull in an icon-font dependency for a static UI pass.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

SIDEBAR_WIDTH = 200


@dataclass(frozen=True, slots=True)
class NavEntry:
    key: str
    icon: str
    label: str
    badge: int | None = None


NAV_SECTIONS: tuple[tuple[str, tuple[NavEntry, ...]], ...] = (
    ("Overview", (NavEntry("dashboard", "▦", "Dashboard"),)),
    ("Connect", (NavEntry("devices", "▭", "Devices"), NavEntry("logcat", "≡", "Logcat"))),
    ("Inspect", (NavEntry("analyzer", "◎", "APK analyzer"), NavEntry("tester", "▶", "Test runner"))),
    ("Protect", (NavEntry("security", "⛨", "Secret scanner", 3), NavEntry("organizer", "▧", "File organizer"))),
    ("Ship", (NavEntry("commands", "▤", "Build commands"), NavEntry("gate", "⌂", "Release gate"), NavEntry("reports", "▥", "Reports"))),
)

SETTINGS_ENTRY = NavEntry("settings", "⚙", "Settings")


class BrandBlock(QWidget):
    """Top-left cell of the shell, sitting beside the environment bar."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("brandBlock")
        self.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)
        layout.addStretch(1)
        title = QLabel("DroidDesk")
        title.setObjectName("brandTitle")
        subtitle = QLabel("local · no account · no upload")
        subtitle.setObjectName("brandSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch(1)


class _NavButton(QPushButton):
    def __init__(self, entry: NavEntry) -> None:
        super().__init__(f"  {entry.icon}   {entry.label}")
        self.setProperty("role", "navItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.key = entry.key


class NavSidebar(QWidget):
    page_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 12)
        outer.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, _NavButton] = {}

        for section_title, entries in NAV_SECTIONS:
            heading = QLabel(section_title.upper())
            heading.setProperty("role", "navSection")
            outer.addWidget(heading)
            for entry in entries:
                outer.addWidget(self._build_row(entry))

        outer.addStretch(1)

        settings_row = self._build_row(SETTINGS_ENTRY)
        outer.addWidget(settings_row)

        self._group.buttonClicked.connect(self._on_clicked)

    def _build_row(self, entry: NavEntry) -> QWidget:
        button = _NavButton(entry)
        self._group.addButton(button)
        self._buttons[entry.key] = button

        if entry.badge is None:
            return button

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        row_layout.addWidget(button, 1)
        badge = QLabel(str(entry.badge))
        badge.setProperty("role", "navBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedWidth(20)
        row_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        row_layout.addSpacing(10)
        return row

    def set_current(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None:
            button.setChecked(True)

    def _on_clicked(self, button: QPushButton) -> None:
        assert isinstance(button, _NavButton)
        self.page_selected.emit(button.key)
