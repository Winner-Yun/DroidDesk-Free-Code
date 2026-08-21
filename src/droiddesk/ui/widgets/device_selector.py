"""Reusable device-picker combo box, shared by every page that needs a target
device (APK Tester, Logcat, Analyzer install action, ...).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox

from droiddesk.core.models import Device


class DeviceSelector(QComboBox):
    device_selected = Signal(object)  # Device | None

    def __init__(self) -> None:
        super().__init__()
        self.currentIndexChanged.connect(self._on_index_changed)

    def set_devices(self, devices: list[Device]) -> None:
        self.clear()
        for device in devices:
            label = f"{device.model or device.serial} ({device.serial})"
            self.addItem(label, device)

    def selected_device(self) -> Device | None:
        return self.currentData()

    def _on_index_changed(self, _index: int) -> None:
        self.device_selected.emit(self.selected_device())
