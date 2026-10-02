"""Device Discovery Service: produces a unified device list from ADB and AVD sources."""

from __future__ import annotations

import contextlib
import re

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from droiddesk.android.avd_manager import AvdManager
from droiddesk.android.emulator_manager import EmulatorManager
from droiddesk.android.models import AvdInfo, EmulatorState
from droiddesk.device.models import DeviceType, ManagedDevice
from droiddesk.infra.adb import AdbClient


class _DiscoveryThread(QThread):
    discovery_finished = Signal(list)  # list[ManagedDevice]

    def __init__(
        self,
        adb_client: AdbClient,
        avd_manager: AvdManager,
        emulator_manager: EmulatorManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._adb = adb_client
        self._avd_mgr = avd_manager
        self._emu_mgr = emulator_manager

    def run(self) -> None:
        unified: list[ManagedDevice] = []

        # 1. Sync emulator manager with active ADB devices
        with contextlib.suppress(Exception):
            self._emu_mgr.sync_with_adb_devices()

        # 2. Query ADB devices
        active_adb_devices: list = []
        with contextlib.suppress(Exception):
            active_adb_devices = self._adb.list_devices()

        # Split physical devices vs active emulator instances
        physical_adb = [d for d in active_adb_devices if not d.serial.startswith("emulator-")]
        running_emulators = [d for d in active_adb_devices if d.serial.startswith("emulator-")]

        # Process Physical Devices
        for dev in physical_adb:
            link = "Wi-Fi" if ":" in dev.serial else "USB"
            status_str = "Ready" if dev.state == "device" else dev.state.capitalize()

            manufacturer: str | None = None
            battery: int | None = None
            screen_size: tuple[int, int] | None = None

            if dev.state == "device":
                props = self._adb.get_all_props(dev.serial)
                manufacturer = props.get("ro.product.manufacturer") or props.get("ro.product.brand")
                battery = self._extract_battery(dev.serial)
                with contextlib.suppress(Exception):
                    screen_size = self._adb.get_screen_size(dev.serial)

            unified.append(
                ManagedDevice(
                    id=f"physical:{dev.serial}",
                    device_type=DeviceType.PHYSICAL,
                    name=dev.model or dev.serial,
                    status=status_str,
                    serial=dev.serial,
                    avd_name=None,
                    model=dev.model,
                    android_version=dev.android_version,
                    api_level=dev.api_level,
                    abi=dev.abi,
                    density=dev.density,
                    manufacturer=manufacturer,
                    battery_level=battery,
                    screen_size=screen_size,
                    link_type=link,
                    is_emulator=False,
                )
            )

        # 3. Query AVD definitions
        avds: list[AvdInfo] = []
        with contextlib.suppress(Exception):
            avds = self._avd_mgr.list_avds()

        # Match running emulators with AVD definitions
        matched_avd_serials: dict[str, str] = {}  # avd_name -> serial
        for emu_dev in running_emulators:
            avd_name = self._emu_mgr.get_avd_name_for_serial(emu_dev.serial)
            if avd_name:
                matched_avd_serials[avd_name] = emu_dev.serial
            elif len(running_emulators) == 1:
                starting_avds = [
                    a.name
                    for a in avds
                    if self._emu_mgr.get_state(a.name)
                    in (EmulatorState.STARTING, EmulatorState.BOOTING)
                ]
                if len(starting_avds) == 1:
                    matched_avd_serials[starting_avds[0]] = emu_dev.serial
                elif len(avds) == 1:
                    matched_avd_serials[avds[0].name] = emu_dev.serial

        for avd in avds:
            serial = matched_avd_serials.get(avd.name)
            emu_state = self._emu_mgr.get_state(avd.name)

            if serial:
                if emu_state in (EmulatorState.STARTING, EmulatorState.BOOTING):
                    boot_completed = ""
                    with contextlib.suppress(Exception):
                        boot_completed = self._adb.getprop(serial, "sys.boot_completed").strip()
                    if boot_completed == "1":
                        self._emu_mgr.set_state(
                            avd.name, EmulatorState.RUNNING, "Android is running."
                        )
                        status_str = "Running"
                    else:
                        status_str = emu_state.value.capitalize()
                else:
                    status_str = "Running"
            else:
                if emu_state in (
                    EmulatorState.STARTING,
                    EmulatorState.BOOTING,
                    EmulatorState.STOPPING,
                ):
                    status_str = emu_state.value.capitalize()
                elif avd.error:
                    status_str = "Error"
                else:
                    status_str = "Stopped"

            model = (
                avd.device_name or avd.config.get("hw.device.name") or avd.name.replace("_", " ")
            )
            api_level: int | None = None
            if avd.target:
                m_api = re.search(r"(\d+)", avd.target)
                if m_api:
                    api_level = int(m_api.group(1))

            android_ver = avd.target or avd.based_on
            abi = avd.abi or avd.config.get("abi.type")
            density: int | None = None
            if "hw.lcd.density" in avd.config and avd.config["hw.lcd.density"].isdigit():
                density = int(avd.config["hw.lcd.density"])

            unified.append(
                ManagedDevice(
                    id=f"virtual:{avd.name}",
                    device_type=DeviceType.VIRTUAL,
                    name=avd.display_name or avd.name.replace("_", " "),
                    status=status_str,
                    serial=serial,
                    avd_name=avd.name,
                    model=model,
                    android_version=android_ver,
                    api_level=api_level,
                    abi=abi,
                    density=density,
                    manufacturer="Google",
                    link_type="Virtual",
                    is_emulator=True,
                    raw_avd=avd,
                    error_message=avd.error,
                )
            )

        self.discovery_finished.emit(unified)

    def _extract_battery(self, serial: str) -> int | None:
        try:
            res = self._adb._runner.run(
                self._adb.adb_path, ["-s", serial, "shell", "dumpsys", "battery"], timeout=3.0
            )
            if res.exit_code == 0:
                for line in res.stdout.splitlines():
                    if "level:" in line:
                        val = line.split(":", 1)[1].strip()
                        if val.isdigit():
                            return int(val)
        except Exception:
            pass
        return None


class DeviceDiscoveryService(QObject):
    """Produces and maintains the unified device list for DroidDesk."""

    devices_changed = Signal(list)  # list[ManagedDevice]

    def __init__(
        self,
        adb_client: AdbClient,
        avd_manager: AvdManager,
        emulator_manager: EmulatorManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._adb = adb_client
        self._avd_mgr = avd_manager
        self._emu_mgr = emulator_manager
        self._devices: list[ManagedDevice] = []
        self._poll_thread: _DiscoveryThread | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh)

        # React to emulator state changes immediately
        self._emu_mgr.state_changed.connect(lambda *_: self.refresh())

    def start_polling(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self.refresh()

    def stop_polling(self) -> None:
        self._timer.stop()

    def set_polling_interval(self, interval_ms: int) -> None:
        self._timer.setInterval(interval_ms)

    def devices(self) -> list[ManagedDevice]:
        return list(self._devices)

    def physical_devices(self) -> list[ManagedDevice]:
        return [d for d in self._devices if d.is_physical]

    def virtual_devices(self) -> list[ManagedDevice]:
        return [d for d in self._devices if d.is_virtual]

    def get_device(self, device_id: str) -> ManagedDevice | None:
        return next((d for d in self._devices if d.id == device_id), None)

    def refresh(self) -> None:
        if self._poll_thread is not None and self._poll_thread.isRunning():
            return
        self._poll_thread = _DiscoveryThread(
            adb_client=self._adb,
            avd_manager=self._avd_mgr,
            emulator_manager=self._emu_mgr,
            parent=self,
        )
        self._poll_thread.discovery_finished.connect(self._on_discovery_finished)
        self._poll_thread.start()

    def _on_discovery_finished(self, fresh_devices: list[ManagedDevice]) -> None:
        if fresh_devices != self._devices:
            self._devices = fresh_devices
            self.devices_changed.emit(list(self._devices))
