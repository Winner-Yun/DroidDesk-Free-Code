"""Dependency wiring: constructs infrastructure, services, and the main window."""

from __future__ import annotations

from droiddesk.config import Settings
from droiddesk.context import AppContext
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.db import Repository
from droiddesk.infra.tools import ToolLocator
from droiddesk.services.device_service import DeviceService
from droiddesk.ui.main_window import MainWindow


def build_application(settings: Settings) -> MainWindow:
    tool_locator = ToolLocator(settings)
    repository = Repository(settings.database_path)
    adb_path = tool_locator.resolve("adb")
    device_service = DeviceService(AdbClient(adb_path))
    ctx = AppContext(
        settings=settings,
        tool_locator=tool_locator,
        repository=repository,
        device_service=device_service,
    )

    # TODO(Phase 2+): construct ApkService, ScanService, EnvService, BuildService,
    #   GateService, OrganizerService, ReportService as each phase lands.

    return MainWindow(ctx)
