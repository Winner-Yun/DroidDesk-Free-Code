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
        prev_dev = self.selected_device()
        prev_serial = prev_dev.serial if prev_dev else None

        self.blockSignals(True)
        self.clear()
        if not devices:
            self.addItem("No device connected", None)
            self.blockSignals(False)
            self.device_selected.emit(None)
            return

        selected_idx = 0
        for i, device in enumerate(devices):
            label = f"{device.model or device.serial} ({device.serial})"
            self.addItem(label, device)
            if prev_serial and device.serial == prev_serial:
                selected_idx = i

        self.setCurrentIndex(selected_idx)
        self.blockSignals(False)

    def selected_device(self) -> Device | None:
        data = self.currentData()
        return data if isinstance(data, Device) else None

    def select_device(self, device: Device | None) -> None:
        if device is None:
            self.setCurrentIndex(-1)
            return
        self.select_serial(device.serial)

    def select_serial(self, serial: str | None) -> None:
        if not serial:
            return
        for i in range(self.count()):
            dev = self.itemData(i)
            if isinstance(dev, Device) and dev.serial == serial:
                if self.currentIndex() != i:
                    self.setCurrentIndex(i)
                return

    def _on_index_changed(self, _index: int) -> None:
        self.device_selected.emit(self.selected_device())
