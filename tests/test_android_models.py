"""Unit tests for Android domain models, environment states, and managed devices."""

from pathlib import Path

from droiddesk.android.models import (
    AndroidEnvState,
    AndroidEnvStatus,
    EmulatorState,
    SystemImage,
)
from droiddesk.device.models import DeviceType, ManagedDevice


def test_android_env_status_ready() -> None:
    status = AndroidEnvStatus(
        state=AndroidEnvState.READY,
        sdk_root=Path("/fake/sdk"),
        adb_path=Path("/fake/sdk/platform-tools/adb"),
        emulator_path=Path("/fake/sdk/emulator/emulator"),
        avdmanager_path=Path("/fake/sdk/cmdline-tools/bin/avdmanager"),
    )
    assert status.is_ready is True


def test_android_env_status_missing_sdk() -> None:
    status = AndroidEnvStatus(
        state=AndroidEnvState.MISSING_SDK,
        error_message="SDK not found",
    )
    assert status.is_ready is False
    assert status.can_manage_physical is False
    assert status.can_manage_virtual is False


def test_emulator_states() -> None:
    assert EmulatorState.STOPPED.value == "STOPPED"
    assert EmulatorState.STARTING.value == "STARTING"
    assert EmulatorState.BOOTING.value == "BOOTING"
    assert EmulatorState.RUNNING.value == "RUNNING"
    assert EmulatorState.STOPPING.value == "STOPPING"


def test_system_image_display_tag() -> None:
    img_play = SystemImage(
        path="system-images;android-35;google_apis_playstore;x86_64",
        api_level=35,
        android_version="15.0",
        tag="google_apis_playstore",
        abi="x86_64",
        is_installed=True,
    )
    assert img_play.display_tag == "Google Play"

    img_api = SystemImage(
        path="system-images;android-34;google_apis;x86_64",
        api_level=34,
        android_version="14.0",
        tag="google_apis",
        abi="x86_64",
        is_installed=False,
    )
    assert img_api.display_tag == "Google APIs"

    img_aosp = SystemImage(
        path="system-images;android-30;default;x86_64",
        api_level=30,
        android_version="11.0",
        tag="default",
        abi="x86_64",
        is_installed=False,
    )
    assert img_aosp.display_tag == "AOSP"


def test_managed_device_properties() -> None:
    phys = ManagedDevice(
        id="physical:test1234",
        device_type=DeviceType.PHYSICAL,
        name="Pixel 8",
        status="Ready",
        serial="test1234",
    )
    assert phys.is_physical is True
    assert phys.is_virtual is False
    assert phys.is_online is True
    assert phys.can_screen_mirror is True
    assert phys.can_install_apk is True

    virt_stopped = ManagedDevice(
        id="virtual:Pixel_8",
        device_type=DeviceType.VIRTUAL,
        name="Pixel 8",
        status="Stopped",
        avd_name="Pixel_8",
    )
    assert virt_stopped.is_physical is False
    assert virt_stopped.is_virtual is True
    assert virt_stopped.is_online is False
    assert virt_stopped.can_screen_mirror is False
