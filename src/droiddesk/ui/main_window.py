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

        # Environment bar with APK selector, upload action, and removal
        self._environment_bar = EnvironmentBar(
            apk_service=self._ctx.apk_service,
            settings=self._settings,
        )
        self._environment_bar.apk_selected.connect(self._on_active_apk_changed)
        self._environment_bar.apks_uploaded.connect(self._on_apks_uploaded)
        self._environment_bar.switch_requested.connect(self._on_switch_environment)
        if self._ctx.env_service:
            self._ctx.env_service.active_environment_changed.connect(
                self._environment_bar.set_environment
            )
            self._environment_bar.set_environment(self._ctx.env_service.active_environment())
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

        # Synchronize initially selected APK with pages
        initial_apk = self._environment_bar.selected_apk()
        self._on_active_apk_changed(initial_apk)

        # TODO(Phase 5): drive the environment bar from
        # EnvService.active_environment_changed instead of static_data.

    def _build_pages(self) -> None:
        for key, page_cls in _PAGES:
            self._page_index[key] = self._stack.addWidget(page_cls(self._ctx))
        if "dashboard" in self._page_index:
            self._page_index["home"] = self._page_index["dashboard"]

        for i in range(self._stack.count()):
            page = self._stack.widget(i)
            if page is not None:
                if hasattr(page, "upload_requested"):
                    page.upload_requested.connect(self._environment_bar._on_upload_clicked)
                if hasattr(page, "navigate_requested"):
                    page.navigate_requested.connect(self._on_navigate_requested)
                if hasattr(page, "findings_changed"):
                    page.findings_changed.connect(
                        lambda c: self._sidebar.set_badge("security", c if c > 0 else None)
                    )

        devices_idx = self._page_index.get("devices")
        if devices_idx is not None:
            devices_widget = self._stack.widget(devices_idx)
            if isinstance(devices_widget, DevicesPage):
                devices_widget.open_logcat_requested.connect(self._on_open_logcat_requested)

    def _on_navigate_requested(self, key: str) -> None:
        if key in self._page_index:
            self._sidebar.set_current(key)
            self._on_page_selected(key)

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        self._status_label = QLabel("Idle")
        bar.addWidget(self._status_label)
        bar.addPermanentWidget(QLabel("tools"))
        tool_status = self._tool_locator.discover_all()
        for name, available in tool_status.items():
            chip = QLabel(name)
            chip.setProperty("role", "toolChip" if available else "toolChipWarn")
            bar.addPermanentWidget(chip)

    def _on_page_selected(self, key: str) -> None:
        # Show the loading screen to create a visual transition
        self.show_loading(f"Loading {key}...")

        def finish_switch() -> None:
            self._stack.setCurrentIndex(self._page_index[key])
            self.hide_loading()

        # Delay the actual switch by a fraction of a second so the animation paints
        QTimer.singleShot(150, finish_switch)

    def _on_open_logcat_requested(self, serial: str) -> None:
        self._sidebar.set_current("logcat")
        self._on_page_selected("logcat")
        logcat_idx = self._page_index.get("logcat")
        if logcat_idx is not None:
            logcat_widget = self._stack.widget(logcat_idx)
            if isinstance(logcat_widget, LogcatPage):
                logcat_widget.select_device(serial)

    def _on_switch_environment(self) -> None:
        if not self._ctx.env_service:
            return
        from droiddesk.ui.dialogs.environment_dialog import EnvironmentSwitchDialog

        dialog = EnvironmentSwitchDialog(self._ctx.env_service, parent=self)
        dialog.exec()

    def show_loading(self, message: str = "Loading...") -> None:
        """Display the loading popup."""
        self._loading_page.set_message(message)
        self._loading_page.show()
        QApplication.processEvents()

    def hide_loading(self) -> None:
        """Hide the loading popup."""
        self._loading_page.hide()

    def _on_active_apk_changed(self, apk_path: Path | None) -> None:
        if apk_path is None:
            self._status_label.setText("Idle")
        else:
            self._status_label.setText(f"Active APK: {apk_path.name}")

        # Notify all pages supporting set_apk or load_apk
        for i in range(self._stack.count()):
            page = self._stack.widget(i)
            if page is not None:
                if hasattr(page, "set_apk"):
                    page.set_apk(apk_path)
                elif hasattr(page, "load_apk"):
                    page.load_apk(apk_path)
                elif hasattr(page, "_on_apk_selected"):
                    page._on_apk_selected(apk_path)

    def _on_apks_uploaded(self, paths: list[Path]) -> None:
        self._status_label.setText(f"Uploaded {len(paths)} APK file(s)")
        device = self._device_bar.selected_device()
        if paths:
            from droiddesk.ui.widgets.device_bar import ApkUploadDialog

            dialog = ApkUploadDialog(
                device_service=self._device_service,
                initial_device=device,
                apk_paths=paths,
                parent=self,
            )
            dialog.exec()
