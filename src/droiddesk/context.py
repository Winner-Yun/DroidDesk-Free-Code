from __future__ import annotations

from dataclasses import dataclass

from droiddesk.config import Settings
from droiddesk.infra.db import Repository
from droiddesk.infra.git import GitClient
from droiddesk.infra.tools import ToolLocator
from droiddesk.services.apk_service import ApkService
from droiddesk.services.build_service import BuildService
from droiddesk.services.device_service import DeviceService
from droiddesk.services.env_service import EnvService
from droiddesk.services.gate_service import GateService
from droiddesk.services.scan_service import ScanService


@dataclass
class AppContext:
    settings: Settings
    tool_locator: ToolLocator
    repository: Repository
    device_service: DeviceService
    apk_service: ApkService
    scan_service: ScanService | None = None
    git_client: GitClient | None = None
    env_service: EnvService | None = None
    build_service: BuildService | None = None
    gate_service: GateService | None = None
