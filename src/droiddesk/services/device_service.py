"""DeviceService - Section 6.1. Polls `adb devices -l` every 2s while the Devices
page is visible, 5s otherwise; enriches entries via getprop. Owns unauthorized /
offline state and Test Device Profile marking. Emits devices_changed; owns no widgets.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from droiddesk.core.errors import DroidDeskError
from droiddesk.core.models import Device
from droiddesk.infra.adb import AdbClient

_POLL_INTERVAL_VISIBLE_MS = 2000
_POLL_INTERVAL_HIDDEN_MS = 5000


class DeviceService(QObject):
    devices_changed = Signal(list)  # list[Device]

    def __init__(self, adb_client: AdbClient) -> None:
        super().__init__()
        self._adb = adb_client
        self._devices: list[Device] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    @property
    def adb_client(self) -> AdbClient:
        return self._adb

    def start_polling(self, page_visible: bool = True) -> None:
        self._timer.setInterval(
            _POLL_INTERVAL_VISIBLE_MS if page_visible else _POLL_INTERVAL_HIDDEN_MS
        )
        self._poll()
        self._timer.start()

    def stop_polling(self) -> None:
        self._timer.stop()

    def set_page_visible(self, visible: bool) -> None:
        self._timer.setInterval(_POLL_INTERVAL_VISIBLE_MS if visible else _POLL_INTERVAL_HIDDEN_MS)

    def devices(self) -> list[Device]:
        return list(self._devices)

    def mark_test_profile(self, serial: str, enabled: bool) -> None:
        for device in self._devices:
            if device.serial == serial:
                device.is_test_profile = enabled
                self.devices_changed.emit(list(self._devices))
                return

    def refresh(self) -> None:
        self._poll()

    def reconnect(self, serial: str) -> None:
        self._adb.reconnect(serial)
        self._poll()

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

    def _poll(self) -> None:
        try:
            fresh = self._adb.list_devices()
        except (DroidDeskError, OSError):
            fresh = []
        # restore in-memory test-profile flags that ADB does not know about
        test_profile_by_serial = {d.serial: d.is_test_profile for d in self._devices}
        for device in fresh:
            device.is_test_profile = test_profile_by_serial.get(device.serial, False)
        if fresh != self._devices:
            self._devices = fresh
            self.devices_changed.emit(list(self._devices))
