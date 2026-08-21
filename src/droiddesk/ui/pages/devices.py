"""Devices page — Section 6.1. Live polling list, explicit unauthorized/offline
states (pairing instruction and reconnect action, not a raw error), wireless
debugging entry, and the Test Device Profile toggle.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget


class DevicesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Devices"))
        self._device_list = QListWidget()
        layout.addWidget(self._device_list)
        self._connect_wireless_button = QPushButton("Connect over Wi-Fi…")
        layout.addWidget(self._connect_wireless_button)

        # TODO(Phase 1): wire to DeviceService.devices_changed; render
        # unauthorized/offline rows distinctly with their recovery actions.
