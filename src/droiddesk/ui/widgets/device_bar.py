from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from droiddesk.services.device_service import DeviceService
from droiddesk.ui.widgets.device_selector import DeviceSelector

class DeviceBar(QWidget):
    def __init__(self, device_service: DeviceService) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._device_label = QLabel("TARGET DEVICE:")
        self._device_selector = DeviceSelector()
        
        layout.addWidget(self._device_label)
        layout.addWidget(self._device_selector)

        device_service.devices_changed.connect(self._device_selector.set_devices)
        self._device_selector.set_devices(device_service.devices())