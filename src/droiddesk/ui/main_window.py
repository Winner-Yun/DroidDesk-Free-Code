"""Application shell — Section 5. A brand block and active-environment bar
across the top, a grouped sidebar over a `QStackedWidget` below it, and a
persistent status bar for the idle/tool-availability strip. This module
contains no business logic and reacts only to service signals, per the
Presentation layer constraint in Section 4.1.
"""


from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
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
from droiddesk.ui.widgets.device_bar import DeviceBar
from droiddesk.ui.widgets.environment_bar import EnvironmentBar
from droiddesk.ui.widgets.loading_spinner import LoadingPage
from droiddesk.ui.widgets.nav_sidebar import BrandBlock, NavSidebar

_PAGES: tuple[tuple[str, Callable[[AppContext], QWidget]], ...] = (
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
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._settings = ctx.settings
        self._tool_locator = ctx.tool_locator
        self._repository = ctx.repository
        self._device_service = ctx.device_service

        self.setWindowTitle("DroidDesk")
        self.resize(1440, 900)
        self.setStyleSheet(STYLESHEET)

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(0)
        top_row.addWidget(BrandBlock())


        # Environment bar with APK selector and Upload action
        self._environment_bar = EnvironmentBar()
        self._environment_bar.apk_selected.connect(self._on_active_apk_changed)
        self._environment_bar.apks_uploaded.connect(self._on_apks_uploaded)
        top_row.addWidget(self._environment_bar, 1)

        # Device selector
        self._device_bar = DeviceBar(self._device_service)
        
        top_row.addSpacing(20)
        top_row.addWidget(self._device_bar)
        top_row.addSpacing(20)
        root_layout.addLayout(top_row)

        body_row = QWidget()
        body_row.setObjectName("bodyRow")
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

        self._loading_page = LoadingPage(parent=self)

        body_layout.addWidget(self._sidebar)
        body_layout.addWidget(self._stack, 1)
        root_layout.addWidget(body_row, 1)
        self.setCentralWidget(root)
        self._build_status_bar()

 
        # TODO(Phase 5): drive the environment bar from
        # EnvService.active_environment_changed instead of static_data.

    def _build_pages(self) -> None:
        for key, page_cls in _PAGES:
            self._page_index[key] = self._stack.addWidget(page_cls(self._ctx))

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
        # Show the loading screen to create a visual transition
        self.show_loading(f"Loading {key}...")
        
        def finish_switch() -> None:
            self._stack.setCurrentIndex(self._page_index[key])
            self.hide_loading()
            
        # Delay the actual switch by a fraction of a second so the animation paints
        QTimer.singleShot(150, finish_switch)

    def _on_switch_environment(self) -> None:
        # TODO(Phase 5): open the environment-switch dialog via EnvService.
        pass

    def show_loading(self, message: str = "Loading...") -> None:
        """Display the loading popup."""
        self._loading_page.set_message(message)
        self._loading_page.show()
        QApplication.processEvents()

    def hide_loading(self) -> None:
        """Hide the loading popup."""
        self._loading_page.hide()

    def _on_active_apk_changed(self, apk_path: Path | None) -> None:
        if not apk_path:
            return
        self.statusBar().showMessage(f"Active APK: {apk_path.name}", 5000)

        # Notify AnalyzerPage
        analyzer_idx = self._page_index.get("analyzer")
        if analyzer_idx is not None:
            analyzer = self._stack.widget(analyzer_idx)
            if analyzer is not None and hasattr(analyzer, "load_apk"):
                analyzer.load_apk(apk_path)

        # Notify ApkTesterPage
        tester_idx = self._page_index.get("tester")
        if tester_idx is not None:
            tester = self._stack.widget(tester_idx)
            if tester is not None and hasattr(tester, "_on_apk_selected"):
                tester._on_apk_selected(apk_path)

    def _on_apks_uploaded(self, paths: list[Path]) -> None:
        self.statusBar().showMessage(f"Uploaded {len(paths)} APK file(s)", 5000)
        device = self._device_bar.selected_device()
        if device and paths:
            from droiddesk.ui.widgets.device_bar import ApkUploadDialog

            dialog = ApkUploadDialog(
                device_service=self._device_service,
                initial_device=device,
                apk_paths=paths,
                parent=self,
            )
            dialog.exec()
