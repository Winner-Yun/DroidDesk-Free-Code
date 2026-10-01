"""Service managing connected Android devices, state polling, hardware details,
and emulator lifecycle.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from droiddesk.android.avd_manager import AvdManager
from droiddesk.android.command_runner import CommandRunner
from droiddesk.android.emulator_manager import EmulatorManager
from droiddesk.android.models import AndroidEnvStatus
from droiddesk.android.sdk_manager import AndroidSdkManager
from droiddesk.application.apk_manager import ApkManager
from droiddesk.config import Settings
from droiddesk.core.errors import DroidDeskError
from droiddesk.core.models import Device
from droiddesk.device.discovery import DeviceDiscoveryService
from droiddesk.device.models import ManagedDevice
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.tools import ToolLocator

_POLL_INTERVAL_VISIBLE_MS = 2000
_POLL_INTERVAL_HIDDEN_MS = 5000


class _DevicePollThread(QThread):
    devices_ready = Signal(list)

    def __init__(self, adb: AdbClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._adb = adb

    def run(self) -> None:
        try:
            devices = self._adb.list_devices()
        except (DroidDeskError, OSError):
            devices = []
        except Exception:
            devices = []
        self.devices_ready.emit(devices)


class DeviceService(QObject):
    devices_changed = Signal(list)  # list[Device] - For backwards compatibility
    managed_devices_changed = Signal(list)  # list[ManagedDevice] - Unified list

    def __init__(
        self,
        adb_client: AdbClient,
        repository: object | None = None,
        tool_locator: ToolLocator | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__()
        self._adb = adb_client
        self._repo = repository
        self._settings = settings or Settings.load()
        self._tool_locator = tool_locator or ToolLocator(self._settings)
        self._runner = CommandRunner(self._tool_locator)

        # Initialize Android Management Subsystems
        self._sdk_manager = AndroidSdkManager(
            self._settings, self._tool_locator, runner=self._runner
        )
        self._avd_manager = AvdManager(self._tool_locator, runner=self._runner)
        self._emulator_manager = EmulatorManager(
            self._tool_locator,
            self._adb,
            runner=self._runner,
            avd_manager=self._avd_manager,
        )
        self._discovery_service = DeviceDiscoveryService(
            self._adb, self._avd_manager, self._emulator_manager, parent=self
        )
        self._apk_manager = ApkManager(self._adb, tool_locator=self._tool_locator)

        self._devices: list[Device] = []
        self._poll_thread: _DevicePollThread | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

        # Wire discovery service signals
        self._discovery_service.devices_changed.connect(self._on_managed_devices_changed)

    @property
    def adb_client(self) -> AdbClient:
        return self._adb

    @property
    def sdk_manager(self) -> AndroidSdkManager:
        return self._sdk_manager

    @property
    def avd_manager(self) -> AvdManager:
        return self._avd_manager

    @property
    def emulator_manager(self) -> EmulatorManager:
        return self._emulator_manager

    @property
    def discovery_service(self) -> DeviceDiscoveryService:
        return self._discovery_service

    @property
    def apk_manager(self) -> ApkManager:
        return self._apk_manager

    def start_polling(self, page_visible: bool = True) -> None:
        interval = _POLL_INTERVAL_VISIBLE_MS if page_visible else _POLL_INTERVAL_HIDDEN_MS
        self._timer.setInterval(interval)
        self._discovery_service.set_polling_interval(interval)
        if not self._timer.isActive():
            self._timer.start()
        self._discovery_service.start_polling()
        QTimer.singleShot(0, self._poll)

    def stop_polling(self) -> None:
        self._timer.stop()
        self._discovery_service.stop_polling()

    def set_page_visible(self, visible: bool) -> None:
        interval = _POLL_INTERVAL_VISIBLE_MS if visible else _POLL_INTERVAL_HIDDEN_MS
        self._timer.setInterval(interval)
        self._discovery_service.set_polling_interval(interval)

    # -------------------------------------------------------------------------
    # Devices retrieval
    # -------------------------------------------------------------------------
    def devices(self) -> list[Device]:
        """Return list of active ADB devices (backwards-compatible with all pages)."""
        return list(self._devices)

    def managed_devices(self) -> list[ManagedDevice]:
        """Return unified list of physical and virtual devices."""
        return self._discovery_service.devices()

    def physical_devices(self) -> list[ManagedDevice]:
        """Return only physical devices."""
        return self._discovery_service.physical_devices()

    def virtual_devices(self) -> list[ManagedDevice]:
        """Return only virtual devices (emulators/AVDs)."""
        return self._discovery_service.virtual_devices()

    def refresh(self) -> None:
        self._poll()
        self._discovery_service.refresh()

    def reconnect(self, serial: str) -> None:
        self._adb.reconnect(serial)
        self.refresh()

    def pair_wireless(self, host_port: str, pairing_code: str) -> bool:
        return self._adb.pair(host_port, pairing_code)

    def connect_wireless(self, host_port: str) -> tuple[bool, str]:
        target = host_port.strip()
        if not target:
            return False, "Host / IP address cannot be empty."
        if ":" not in target:
            target = f"{target}:5555"
        success, message = self._adb.connect(target)
        if success:
            self.refresh()
        return success, message

    def take_screenshot(self, serial: str, dest_dir: Path | None = None) -> Path:
        from datetime import datetime

        target_dir = dest_dir or (Path.home() / "Pictures" / "DroidDesk")
        target_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_serial = "".join(c if c.isalnum() else "_" for c in serial)
        file_path = target_dir / f"screenshot_{safe_serial}_{timestamp}.png"

        png_bytes = self._adb.screenshot(serial)
        is_valid = bool(
            png_bytes
            and len(png_bytes) >= 8
            and (png_bytes.startswith(b"\x89PNG") or b"PNG" in png_bytes[:16])
        )
        if not is_valid:
            raise DroidDeskError(f"Device '{serial}' returned invalid or empty screenshot data.")

        file_path.write_bytes(png_bytes)
        return file_path

    def install_apk(
        self, serial: str, apk_path: Path, replace: bool = True, test_ok: bool = True
    ) -> bool:
        return self._adb.install(serial, apk_path, replace=replace, test_ok=test_ok)

    # -------------------------------------------------------------------------
    # Virtual Device / Emulator Operations
    # -------------------------------------------------------------------------
    def start_emulator(self, avd_name: str) -> None:
        """Start an emulator asynchronously."""
        self._emulator_manager.start_emulator(avd_name)

    def stop_emulator(self, avd_name: str) -> None:
        """Stop an emulator asynchronously."""
        self._emulator_manager.stop_emulator(avd_name)

    def restart_emulator(self, avd_name: str) -> None:
        """Restart an emulator asynchronously."""
        self._emulator_manager.restart_emulator(avd_name)

    def delete_emulator(self, avd_name: str) -> tuple[bool, str]:
        """Delete an emulator AVD and refresh discovery."""
        success, msg = self._avd_manager.delete_avd(avd_name)
        if success:
            self.refresh()
        return success, msg

    def force_release_emulator_locks(self, avd_name: str) -> tuple[bool, str]:
        """Force-release session locks and clean up stuck processes for an AVD."""
        res, msg = self._emulator_manager.force_release_locks(avd_name)
        self.refresh()
        return res, msg

    def check_environment(self) -> AndroidEnvStatus:
        """Check status of Android SDK and CLI tools."""
        return self._sdk_manager.check_environment()

    # -------------------------------------------------------------------------
    # Internal Polling and Signal Handlers
    # -------------------------------------------------------------------------
    def _poll(self) -> None:
        if self._poll_thread is not None and self._poll_thread.isRunning():
            return
        self._poll_thread = _DevicePollThread(self._adb, self)
        self._poll_thread.devices_ready.connect(self._on_poll_finished)
        self._poll_thread.start()

    def _on_poll_finished(self, fresh: list[Device]) -> None:
        if self._repo is not None and hasattr(self._repo, "record_device"):
            for device in fresh:
                with contextlib.suppress(Exception):
                    self._repo.record_device(device)
        if fresh != self._devices:
            self._devices = fresh
            self.devices_changed.emit(list(self._devices))

    def _on_managed_devices_changed(self, fresh_managed: list[ManagedDevice]) -> None:
        self.managed_devices_changed.emit(list(fresh_managed))
