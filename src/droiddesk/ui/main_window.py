"""Application shell — Section 5. Sidebar navigation over a QStackedWidget, a
persistent status bar (used for the active-environment indicator, Section 6.8),
and nothing else: this module contains no business logic and reacts only to
service signals, per the Presentation layer constraint in Section 4.1.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QMainWindow, QSplitter, QStackedWidget, QWidget

from droiddesk.config import Settings
from droiddesk.infra.db import Repository
from droiddesk.infra.tools import ToolLocator
from droiddesk.ui.pages.dashboard import DashboardPage
from droiddesk.ui.pages.devices import DevicesPage
from droiddesk.ui.theme import STYLESHEET

_PAGES: tuple[tuple[str, type[QWidget]], ...] = (
    ("Dashboard", DashboardPage),
    ("Devices", DevicesPage),
    # TODO: register ApkTesterPage, LogcatPage, AnalyzerPage, SecurityPage,
    # OrganizerPage, CommandsPage, ReportsPage as each phase lands them.
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
        self.resize(1280, 800)
        self.setStyleSheet(STYLESHEET)

        self._sidebar = QListWidget(objectName="sidebar")
        self._stack = QStackedWidget()
        self._build_pages()

        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._sidebar.setCurrentRow(0)

        splitter = QSplitter()
        splitter.addWidget(self._sidebar)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 1080])
        self.setCentralWidget(splitter)

        self._environment_label = QLabel("No environment active")
        self.statusBar().addPermanentWidget(self._environment_label)

        # TODO(Phase 5): drive self._environment_label from
        # EnvService.active_environment_changed, coloured by risk (Section 6.8).

    def _build_pages(self) -> None:
        for label, page_cls in _PAGES:
            self._sidebar.addItem(label)
            self._stack.addWidget(page_cls())
