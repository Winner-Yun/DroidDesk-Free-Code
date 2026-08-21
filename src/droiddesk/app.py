"""Dependency wiring: constructs infrastructure, services, and the main window."""

from __future__ import annotations

from droiddesk.config import Settings
from droiddesk.infra.db import Repository
from droiddesk.infra.tools import ToolLocator
from droiddesk.ui.main_window import MainWindow


def build_application(settings: Settings) -> MainWindow:
    tool_locator = ToolLocator(settings)
    repository = Repository(settings.database_path)

    # TODO(Phase 1): construct DeviceService and wire it into MainWindow.
    # TODO(Phase 2+): construct ApkService, ScanService, EnvService, BuildService,
    #   GateService, OrganizerService, ReportService as each phase lands.

    return MainWindow(settings=settings, tool_locator=tool_locator, repository=repository)
