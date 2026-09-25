"""Dependency wiring: constructs infrastructure, services, and the main window."""

from __future__ import annotations

from pathlib import Path

from droiddesk.config import Settings
from droiddesk.context import AppContext
from droiddesk.core.errors import ToolNotFoundError
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.apk_reader import ApkReader
from droiddesk.infra.db import Repository
from droiddesk.infra.git import GitClient
from droiddesk.infra.tools import ToolLocator
from droiddesk.services.apk_service import ApkService
from droiddesk.services.build_service import BuildService
from droiddesk.services.device_service import DeviceService
from droiddesk.services.env_service import EnvService
from droiddesk.services.organizer_service import OrganizerService
from droiddesk.services.report_service import ReportService
from droiddesk.services.scan_service import ScanService
from droiddesk.services.test_service import CrashDetector, TestStateMachine
from droiddesk.ui.main_window import MainWindow


def build_application(settings: Settings) -> MainWindow:
    tool_locator = ToolLocator(settings)
    if not tool_locator.is_available("adb"):
        from droiddesk.ui.dialogs.setup_dialog import SetupDialog

        dlg = SetupDialog(settings, tool_locator)
        dlg.exec()
        tool_locator.invalidate_cache()

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

    apk_reader = ApkReader(tool_locator=tool_locator)
    crash_detector = CrashDetector()
    state_machine = TestStateMachine(
        adb_client=adb_client,
        apk_reader=apk_reader,
        crash_detector=crash_detector,
    )
    apk_service = ApkService(
        apk_reader,
        adb_client,
        apkanalyzer_path,
        state_machine=state_machine,
        crash_detector=crash_detector,
        repository=repository,
        storage_dir=settings.data_dir / "apks",
    )

    scan_service = ScanService(tool_locator=tool_locator, apk_reader=apk_reader)
    git_client = GitClient(tool_locator=tool_locator)
    env_service = EnvService(project_root=Path.cwd())
    envs = env_service.load_environments()
    if envs:
        default_env = next((e for e in envs if not e.allow_release_build), envs[0])
        env_service.set_active_environment(default_env)
    build_service = BuildService(
        env_service=env_service,
        scan_service=scan_service,
        git_client=git_client,
        apk_service=apk_service,
        repository=repository,
    )
    organizer_service = OrganizerService(journal_dir=settings.data_dir / "journals")
    report_service = ReportService()

    ctx = AppContext(
        settings=settings,
        tool_locator=tool_locator,
        repository=repository,
        device_service=device_service,
        apk_service=apk_service,
        scan_service=scan_service,
        git_client=git_client,
        env_service=env_service,
        build_service=build_service,
        organizer_service=organizer_service,
        report_service=report_service,
    )

    return MainWindow(ctx)
