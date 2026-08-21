"""Application shell — Section 5. A brand block and active-environment bar
across the top, a grouped sidebar over a `QStackedWidget` below it, and a
persistent status bar for the idle/tool-availability strip. This module
contains no business logic and reacts only to service signals, per the
Presentation layer constraint in Section 4.1.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from droiddesk.config import Settings
from droiddesk.infra.db import Repository
from droiddesk.infra.tools import ToolLocator
from droiddesk.ui import static_data
from droiddesk.ui.pages.analyzer import AnalyzerPage
from droiddesk.ui.pages.apk_tester import ApkTesterPage
from droiddesk.ui.pages.commands import CommandsPage
from droiddesk.ui.pages.dashboard import DashboardPage
from droiddesk.ui.pages.devices import DevicesPage
from droiddesk.ui.pages.gate import GatePage
from droiddesk.ui.pages.logcat import LogcatPage
from droiddesk.ui.pages.organizer import OrganizerPage
from droiddesk.ui.pages.reports import ReportsPage
from droiddesk.ui.pages.security import SecurityPage
from droiddesk.ui.pages.settings import SettingsPage
from droiddesk.ui.theme import STYLESHEET
from droiddesk.ui.widgets.environment_bar import EnvironmentBar
from droiddesk.ui.widgets.nav_sidebar import BrandBlock, NavSidebar

_PAGES: tuple[tuple[str, type[QWidget]], ...] = (
    ("dashboard", DashboardPage),
    ("devices", DevicesPage),
    ("logcat", LogcatPage),
    ("analyzer", AnalyzerPage),
    ("tester", ApkTesterPage),
    ("security", SecurityPage),
    ("organizer", OrganizerPage),
    ("commands", CommandsPage),
    ("gate", GatePage),
    ("reports", ReportsPage),
    ("settings", SettingsPage),
)


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: Settings,
        tool_locator: ToolLocator,
        repository: Repository,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._tool_locator = tool_locator
        self._repository = repository

        self.setWindowTitle("DroidDesk")
        self.resize(1440, 900)
        self.setStyleSheet(STYLESHEET)

        root = QWidget(objectName="appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        top_row.addWidget(BrandBlock())
        self._environment_bar = EnvironmentBar()
        self._environment_bar.switch_requested.connect(self._on_switch_environment)
        top_row.addWidget(self._environment_bar, 1)
        root_layout.addLayout(top_row)

        body_row = QWidget(objectName="bodyRow")
        body_layout = QHBoxLayout(body_row)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._sidebar = NavSidebar()
        self._stack = QStackedWidget()
        self._page_index: dict[str, int] = {}
        self._build_pages()

        self._sidebar.page_selected.connect(self._on_page_selected)
        self._sidebar.set_current("dashboard")
        self._stack.setCurrentIndex(self._page_index["dashboard"])

        body_layout.addWidget(self._sidebar)
        body_layout.addWidget(self._stack, 1)
        root_layout.addWidget(body_row, 1)

        self.setCentralWidget(root)
        self._build_status_bar()

        self._environment_bar.set_environment(
            static_data.ACTIVE_ENVIRONMENT_KEY,
            static_data.ACTIVE_ENVIRONMENT_LABEL,
            static_data.ACTIVE_ENVIRONMENT_HOST,
            static_data.ACTIVE_ENVIRONMENT_NOTE,
        )
        # TODO(Phase 5): drive the environment bar from
        # EnvService.active_environment_changed instead of static_data.

    def _build_pages(self) -> None:
        for key, page_cls in _PAGES:
            self._page_index[key] = self._stack.addWidget(page_cls())

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.addWidget(QLabel(static_data.STATUS_MESSAGE))
        bar.addPermanentWidget(QLabel("tools"))
        for name, available in static_data.TOOL_STATUS:
            chip = QLabel(name)
            chip.setProperty("role", "toolChip" if available else "toolChipWarn")
            bar.addPermanentWidget(chip)
        # TODO(Phase 1+): replace the static tool strip with
        # ToolLocator.discover() results, and the idle label with real
        # service activity (scan running, test running, ...).

    def _on_page_selected(self, key: str) -> None:
        self._stack.setCurrentIndex(self._page_index[key])

    def _on_switch_environment(self) -> None:
        # TODO(Phase 5): open the environment-switch dialog via EnvService.
        pass
