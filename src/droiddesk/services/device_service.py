"""DeviceService — Section 6.1. Polls `adb devices -l` every 2s while the Devices
page is visible, 5s otherwise; enriches entries via getprop. Owns unauthorized /
offline state and Test Device Profile marking. Emits devices_changed; owns no widgets.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

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

    def start_polling(self, page_visible: bool = True) -> None:
        self._timer.setInterval(
            _POLL_INTERVAL_VISIBLE_MS if page_visible else _POLL_INTERVAL_HIDDEN_MS
        )
        self._timer.start()

    def stop_polling(self) -> None:
        self._timer.stop()

    def set_page_visible(self, visible: bool) -> None:
        self._timer.setInterval(
            _POLL_INTERVAL_VISIBLE_MS if visible else _POLL_INTERVAL_HIDDEN_MS
        )

    def devices(self) -> list[Device]:
        return list(self._devices)

    def mark_test_profile(self, serial: str, enabled: bool) -> None:
        # TODO(Phase 1): persist the allowed-environment policy for this device.
        raise NotImplementedError

    def pair_wireless(self, host_port: str, pairing_code: str) -> bool:
        return self._adb.pair(host_port, pairing_code)

    def _poll(self) -> None:
        # TODO(Phase 1): self._devices = self._adb.list_devices(); diff and emit
        # devices_changed only when the list actually changes.
        raise NotImplementedError
