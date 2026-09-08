"""Dependency wiring: constructs infrastructure, services, and the main window."""

from __future__ import annotations

from pathlib import Path

from droiddesk.config import Settings
from droiddesk.context import AppContext
from droiddesk.core.errors import ToolNotFoundError
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.db import Repository
from droiddesk.infra.tools import ToolLocator
from droiddesk.services.device_service import DeviceService
from droiddesk.infra.apk_reader import ApkReader
from droiddesk.services.apk_service import ApkService
from droiddesk.ui.main_window import MainWindow


def build_application(settings: Settings) -> MainWindow:
    tool_locator = ToolLocator(settings)
    repository = Repository(settings.database_path)
    try:
        adb_path = tool_locator.resolve("adb")
    except ToolNotFoundError:
        adb_path = Path("adb.exe")
        
    adb_client = AdbClient(adb_path)
    device_service = DeviceService(adb_client)
    device_service.start_polling()
    
    try:
        apkanalyzer_path = tool_locator.resolve("apkanalyzer")
    except ToolNotFoundError:
        apkanalyzer_path = Path("apkanalyzer.bat")
        
    apk_reader = ApkReader()
    apk_service = ApkService(apk_reader, adb_client, apkanalyzer_path)
    
    ctx = AppContext(
        settings=settings,
        tool_locator=tool_locator,
        repository=repository,
        device_service=device_service,
        apk_service=apk_service,
    )

    # TODO(Phase 2+): construct ScanService, EnvService, BuildService,
    #   GateService, OrganizerService, ReportService as each phase lands.

    return MainWindow(ctx)
