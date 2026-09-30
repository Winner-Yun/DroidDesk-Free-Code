"""Main application window managing top navigation, sidebar, and page views."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
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
from droiddesk.ui.pages.logcat import LogcatPage
from droiddesk.ui.pages.organizer import OrganizerPage
from droiddesk.ui.pages.recordings import RecordingsPage
from droiddesk.ui.pages.screen import ScreenMirrorPage
from droiddesk.ui.pages.screenshots import ScreenshotsPage
from droiddesk.ui.pages.security import SecurityPage
from droiddesk.ui.pages.settings import SettingsPage
from droiddesk.ui.theme import get_app_logo_icon, get_stylesheet
from droiddesk.ui.widgets.device_bar import DeviceBar
from droiddesk.ui.widgets.environment_bar import EnvironmentBar
from droiddesk.ui.widgets.nav_sidebar import BrandBlock, NavSidebar

_PAGES: tuple[tuple[str, Callable[[AppContext], QWidget]], ...] = (
    ("dashboard", DashboardPage),
    ("devices", DevicesPage),
    ("screen", ScreenMirrorPage),
    ("logcat", LogcatPage),
    ("screenshots", ScreenshotsPage),
    ("recordings", RecordingsPage),
    ("analyzer", AnalyzerPage),
    ("tester", ApkTesterPage),
    ("security", SecurityPage),
    ("organizer", OrganizerPage),
    ("commands", CommandsPage),
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
        self.setWindowIcon(get_app_logo_icon())
        self.resize(1440, 900)
        self.setStyleSheet(get_stylesheet(self._settings.theme_mode))

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._top_bar = QWidget()
        top_row = QHBoxLayout(self._top_bar)
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
        root_layout.addWidget(self._top_bar)

        body_row = QWidget()
        body_row.setObjectName("bodyRow")
        body_layout = QHBoxLayout(body_row)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._sidebar = NavSidebar(theme_mode=self._settings.theme_mode)
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

        # Synchronize initially selected APK with pages
        initial_apk = self._environment_bar.selected_apk()
        self._on_active_apk_changed(initial_apk)

    def set_theme(self, mode: str) -> None:
        self.setStyleSheet(get_stylesheet(mode))
        if hasattr(self, "_sidebar") and hasattr(self._sidebar, "update_theme"):
            self._sidebar.update_theme(mode)
        if hasattr(self, "_environment_bar") and hasattr(self._environment_bar, "set_theme"):
            self._environment_bar.set_theme(mode)
        for i in range(self._stack.count()):
            page = self._stack.widget(i)
            if page is not None and hasattr(page, "set_theme"):
                page.set_theme(mode)



    def enter_mirror_fullscreen(self) -> None:
        self._top_bar.setVisible(False)
        self._sidebar.setVisible(False)
        self.statusBar().setVisible(False)
        self.showFullScreen()

    def exit_mirror_fullscreen(self) -> None:
        self._top_bar.setVisible(True)
        self._sidebar.setVisible(True)
        self.statusBar().setVisible(True)
        self.showNormal()

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

        devices_idx = self._page_index.get("devices")
        if devices_idx is not None:
            devices_widget = self._stack.widget(devices_idx)
            if isinstance(devices_widget, DevicesPage):
                devices_widget.open_logcat_requested.connect(self._on_open_logcat_requested)
                devices_widget.open_screen_requested.connect(self._on_open_screen_requested)

        screen_idx = self._page_index.get("screen")
        if screen_idx is not None:
            screen_widget = self._stack.widget(screen_idx)
            if screen_widget is not None and hasattr(screen_widget, "fullscreen_requested"):
                screen_widget.fullscreen_requested.connect(
                    lambda fs: (
                        self.enter_mirror_fullscreen() if fs else self.exit_mirror_fullscreen()
                    )
                )

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
        if key in self._page_index:
            self._stack.setCurrentIndex(self._page_index[key])

    def _on_open_screen_requested(self, serial: str) -> None:
        self._sidebar.set_current("screen")
        self._on_page_selected("screen")
        screen_idx = self._page_index.get("screen")
        if screen_idx is not None:
            screen_widget = self._stack.widget(screen_idx)
            if isinstance(screen_widget, ScreenMirrorPage):
                screen_widget.select_device(serial)

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
        """Disabled - loading spinner removed."""
        pass

    def hide_loading(self) -> None:
        """Disabled - loading spinner removed."""
        pass


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
