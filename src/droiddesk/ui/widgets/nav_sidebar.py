"""Application shell navigation — Section 5. A grouped, badge-aware sidebar
(Overview / Connect / Inspect / Protect / Ship, with Settings pinned to the
bottom) replaces the flat `QListWidget` the scaffold started with, matching
the approved mockups.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from droiddesk.ui.theme import TEXT, TEXT_MUTED, get_app_logo_pixmap, get_icon

SIDEBAR_WIDTH = 200


@dataclass(frozen=True, slots=True)
class NavEntry:
    key: str
    icon: str
    label: str
    badge: int | None = None


NAV_SECTIONS: tuple[tuple[str, tuple[NavEntry, ...]], ...] = (
    ("Overview", (NavEntry("dashboard", "house", "Home"),)),
    (
        "Connect",
        (
            NavEntry("devices", "smartphone", "Devices"),
            NavEntry("logcat", "scroll-text", "Logcat"),
        ),
    ),
    (
        "Inspect",
        (
            NavEntry("analyzer", "package-search", "APK analyzer"),
            NavEntry("tester", "play", "Test runner"),
        ),
    ),
    (
        "Protect",
        (
            NavEntry("security", "shield-check", "Secret scanner"),
            NavEntry("organizer", "folder-cog", "File organizer"),
        ),
    ),
    (
        "Ship",
        (
            NavEntry("commands", "terminal", "Build commands"),
            NavEntry("gate", "door-open", "Release gate"),
            NavEntry("reports", "file-text", "Reports"),
        ),
    ),
)

SETTINGS_ENTRY = NavEntry("settings", "settings", "Settings")


class BrandBlock(QWidget):
    """Top-left cell of the shell, sitting beside the environment bar."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("brandBlock")
        self.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(2)
        layout.addStretch(1)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        logo_lbl = QLabel()
        logo_lbl.setFixedSize(26, 26)
        logo_lbl.setPixmap(get_app_logo_pixmap(size=26))
        title_row.addWidget(logo_lbl)

        title = QLabel("DroidDesk")
        title.setObjectName("brandTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        subtitle = QLabel("local · no account · no upload")
        subtitle.setObjectName("brandSubtitle")
        layout.addWidget(subtitle)
        layout.addStretch(1)


class _NavButton(QPushButton):
    def __init__(self, entry: NavEntry) -> None:
        super().__init__(f"  {entry.label}")
        self.setProperty("role", "navItem")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(get_icon(entry.icon, size=16, color=TEXT_MUTED, active_color=TEXT))
        self.setIconSize(QSize(16, 16))
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
