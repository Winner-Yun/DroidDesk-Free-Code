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
    ("Overview", (NavEntry("dashboard", "▦", "Home"),)),
    ("Connect", (NavEntry("devices", "▭", "Devices"), NavEntry("logcat", "≡", "Logcat"))),
    (
        "Inspect",
        (NavEntry("analyzer", "◎", "APK analyzer"), NavEntry("tester", "▶", "Test runner")),
    ),
    (
        "Protect",
        (
            NavEntry("security", "⛨", "Secret scanner"),
            NavEntry("organizer", "▧", "File organizer"),
        ),
    ),
    (
        "Ship",
        (
            NavEntry("commands", "▤", "Build commands"),
            NavEntry("gate", "⌂", "Release gate"),
            NavEntry("reports", "▥", "Reports"),
        ),
    ),
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

        badge_layout = QHBoxLayout(self)
        badge_layout.setContentsMargins(0, 0, 10, 0)
        badge_layout.addStretch(1)

        self._badge = QLabel(self)
        self._badge.setProperty("role", "navBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._badge.hide()
        badge_layout.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignVCenter)

        if entry.badge is not None and entry.badge > 0:
            self.set_badge(entry.badge)

    def set_badge(self, count: int | None) -> None:
        if count is not None and count > 0:
            self._badge.setText(str(count))
            self._badge.show()
        else:
            self._badge.hide()


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
        return button

    def set_badge(self, key: str, count: int | None) -> None:
        button = self._buttons.get(key)
        if button is not None:
            button.set_badge(count)

    def set_current(self, key: str) -> None:
        target_key = "dashboard" if key == "home" else key
        button = self._buttons.get(target_key)
        if button is not None:
            button.setChecked(True)

    def _on_clicked(self, button: QPushButton) -> None:
        assert isinstance(button, _NavButton)
        self.page_selected.emit(button.key)
