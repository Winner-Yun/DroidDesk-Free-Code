"""Unified Device Model representing both physical Android devices and virtual emulators."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from droiddesk.android.models import AvdInfo


class DeviceType(StrEnum):
    PHYSICAL = "PHYSICAL"
    VIRTUAL = "VIRTUAL"


@dataclass(slots=True)
class ManagedDevice:
    """Unified representation of a physical Android device or virtual emulator."""

    id: str  # Unique stable ID: "physical:<serial>" or "virtual:<avd_name>"
    device_type: DeviceType
    name: str  # Human-readable display name
    status: str  # e.g. Ready, Connected, Unauthorized, Offline, Stopped, Booting, Running
    serial: str | None = None  # ADB serial if active / running
    avd_name: str | None = None  # AVD identifier if virtual
    model: str | None = None
    android_version: str | None = None
    api_level: int | None = None
    abi: str | None = None
    density: int | None = None
    manufacturer: str | None = None
    battery_level: int | None = None
    screen_size: tuple[int, int] | None = None
    link_type: str = "USB"  # USB | Wi-Fi
    is_emulator: bool = False
    raw_avd: AvdInfo | None = None
    error_message: str | None = None

    @property
    def is_physical(self) -> bool:
        return self.device_type == DeviceType.PHYSICAL

    @property
    def is_virtual(self) -> bool:
        return self.device_type == DeviceType.VIRTUAL

    @property
    def is_online(self) -> bool:
        """Return True if device is active and responsive to ADB commands."""
        if self.is_physical:
            return self.status.lower() in ("ready", "device", "connected")
        return bool(self.serial) and self.status.lower() in (
            "running",
            "booting",
            "ready",
            "device",
        )

    @property
    def can_screen_mirror(self) -> bool:
        return bool(self.serial) and self.status.lower() in (
            "running",
            "booting",
            "ready",
            "device",
        )

    @property
    def can_install_apk(self) -> bool:
        return bool(self.serial) and self.status.lower() in (
            "running",
            "booting",
            "ready",
            "device",
        )

    @property
    def can_view_logs(self) -> bool:
        return bool(self.serial) and self.status.lower() in (
            "running",
            "booting",
            "ready",
            "device",
        )
