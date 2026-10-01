"""Unit tests for AvdManager parsing logic."""

from unittest.mock import MagicMock

from droiddesk.android.avd_manager import AvdManager
from droiddesk.android.command_runner import CommandResult
from droiddesk.config import Settings
from droiddesk.infra.tools import ToolLocator

_MOCK_LIST_AVD_OUTPUT = """
Available Android Virtual Devices:
    Name: Pixel_8_Test
  Device: pixel_8 (Google)
    Path: C:\\Users\\User\\.android\\avd\\Pixel_8_Test.avd
  Target: Google Play (Google Inc.)
          Based on: Android 15.0 ("VanillaIceCream") Tag/ABI: google_apis_playstore/x86_64
    Skin: pixel_8
  Sdcard: 512M
---------
The following Android Virtual Devices could not be loaded:
    Name: Broken_AVD
    Path: C:\\Users\\User\\.android\\avd\\Broken_AVD.avd
   Error: Missing system image for Google APIs x86_64.
"""

_MOCK_LIST_DEVICE_OUTPUT = """
Available devices definitions:
id: 0 or "pixel_8"
    Name: Pixel 8
    OEM : Google
    Tag : android-playstore
---------
id: 1 or "pixel_7"
    Name: Pixel 7
    OEM : Google
    Tag : android-playstore
---------
id: 2 or "tablet_10"
    Name: 10in Tablet
    OEM : Generic
"""


def test_parse_avdmanager_list_avd() -> None:
    s = Settings()
    tl = ToolLocator(s)
    mgr = AvdManager(tl)

    avds = mgr._parse_avdmanager_list_avd(_MOCK_LIST_AVD_OUTPUT)
    assert len(avds) == 2

    # First AVD: valid
    a0 = avds[0]
    assert a0.name == "Pixel_8_Test"
    assert a0.display_name == "Pixel 8 Test"
    assert a0.device_name == "pixel_8 (Google)"
    assert a0.target == "Google Play (Google Inc.)"
    assert a0.abi == "google_apis_playstore/x86_64"
    assert a0.error is None

    # Second AVD: broken
    a1 = avds[1]
    assert a1.name == "Broken_AVD"
    assert a1.error == "Missing system image for Google APIs x86_64."


def test_parse_avdmanager_list_device() -> None:
    s = Settings()
    tl = ToolLocator(s)
    mgr = AvdManager(tl)

    profiles = mgr._parse_device_profiles(_MOCK_LIST_DEVICE_OUTPUT)
    assert len(profiles) == 3

    assert profiles[0].id == "pixel_8"
    assert profiles[0].name == "Pixel 8"
    assert profiles[0].oem == "Google"

    assert profiles[1].id == "pixel_7"
    assert profiles[1].name == "Pixel 7"

    assert profiles[2].id == "tablet_10"
    assert profiles[2].name == "10in Tablet"
    assert profiles[2].oem == "Generic"


def test_delete_avd_empty_name() -> None:
    s = Settings()
    tl = ToolLocator(s)
    mgr = AvdManager(tl)
    ok, msg = mgr.delete_avd("   ")
    assert not ok
    assert "empty" in msg.lower()


def test_delete_avd_cli_success(monkeypatch, tmp_path) -> None:
    s = Settings()
    tl = ToolLocator(s)
    mock_runner = MagicMock()
    mock_runner.run.return_value = CommandResult(
        exit_code=0, stdout="AVD deleted", stderr="", duration_s=0.1, command=["avdmanager"]
    )

    mgr = AvdManager(tl, runner=mock_runner)
    monkeypatch.setattr(AvdManager, "avd_root_dir", property(lambda self: tmp_path))

    ok, msg = mgr.delete_avd("Test_AVD")
    assert ok
    assert "removed successfully" in msg
    mock_runner.run.assert_called_once()


def test_delete_avd_fallback_file_removal(monkeypatch, tmp_path) -> None:
    s = Settings()
    tl = ToolLocator(s)
    mock_runner = MagicMock()
    # CLI fails (e.g. broken AVD or missing image)
    mock_runner.run.return_value = CommandResult(
        exit_code=1, stdout="", stderr="Error: broken AVD", duration_s=0.1, command=["avdmanager"]
    )

    mgr = AvdManager(tl, runner=mock_runner)
    monkeypatch.setattr(AvdManager, "avd_root_dir", property(lambda self: tmp_path))

    # Create dummy files
    ini_file = tmp_path / "Broken_Emu.ini"
    ini_file.write_text("dummy=true\n", encoding="utf-8")
    avd_folder = tmp_path / "Broken_Emu.avd"
    avd_folder.mkdir()
    (avd_folder / "config.ini").write_text("AvdId=Broken_Emu\n", encoding="utf-8")

    ok, msg = mgr.delete_avd("Broken_Emu")
    assert ok
    assert "removed successfully" in msg
    assert not ini_file.exists()
    assert not avd_folder.exists()
