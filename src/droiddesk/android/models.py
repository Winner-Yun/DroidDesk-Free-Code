"""Domain models and state definitions for Android SDK, AVD, and Emulator management."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class AndroidEnvState(StrEnum):
    READY = "READY"
    MISSING_SDK = "MISSING_SDK"
    MISSING_ADB = "MISSING_ADB"
    MISSING_EMULATOR = "MISSING_EMULATOR"
    MISSING_AVDMANAGER = "MISSING_AVDMANAGER"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


class EmulatorState(StrEnum):
    CREATED = "CREATED"
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    BOOTING = "BOOTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    ERROR = "ERROR"
    DELETING = "DELETING"


@dataclass(slots=True)
class AndroidEnvStatus:
    state: AndroidEnvState = AndroidEnvState.ERROR
    sdk_root: Path | None = None
    adb_path: Path | None = None
    emulator_path: Path | None = None
    avdmanager_path: Path | None = None
    sdkmanager_path: Path | None = None
    java_home: Path | None = None
    adb_version: str | None = None
    emulator_version: str | None = None
    sdkmanager_version: str | None = None
    details: dict[str, str] = field(default_factory=dict)
    error_message: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.state == AndroidEnvState.READY

    @property
    def can_manage_physical(self) -> bool:
        return self.adb_path is not None and self.adb_path.is_file()

    @property
    def can_manage_virtual(self) -> bool:
        return (
            self.emulator_path is not None
            and self.emulator_path.is_file()
            and self.avdmanager_path is not None
            and self.avdmanager_path.is_file()
        )


@dataclass(slots=True)
class AvdInfo:
    name: str
    display_name: str
    device_name: str | None = None
    path: Path | None = None
    target: str | None = None
    based_on: str | None = None
    abi: str | None = None
    skin: str | None = None
    sdcard: str | None = None
    error: str | None = None
    config: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DeviceProfile:
    id: str
    name: str
    oem: str = "Google"
    tag: str | None = None
    screen_size: str | None = None
    resolution: str | None = None
    ram_default: str | None = None


@dataclass(slots=True)
class SystemImage:
    path: str  # e.g. "system-images;android-35;google_apis_playstore;x86_64"
    api_level: int
    android_version: str
    tag: str  # google_apis_playstore | google_apis | default / aosp
    abi: str  # x86_64 | arm64-v8a | x86
    is_installed: bool = False
    location: Path | None = None

    @property
    def display_tag(self) -> str:
        if "playstore" in self.tag:
            return "Google Play"
        elif "google_apis" in self.tag:
            return "Google APIs"
        return "AOSP"
