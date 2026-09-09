from pathlib import Path
from unittest.mock import MagicMock

import pytest

from droiddesk.core.models import ApkInfo
from droiddesk.core.profiles import TestProfile
from droiddesk.core.severity import Verdict
from droiddesk.services.test_service import CrashDetector, TestStateMachine


def test_crash_detector_evaluates_clean_logs() -> None:
    detector = CrashDetector()
    lines = [
        "09-09 10:00:00.000 123 123 D MyApp: Initializing components",
        "09-09 10:00:01.000 123 123 I MyApp: Activity resumed",
    ]
    verdict, matches = detector.evaluate(lines)
    assert verdict == Verdict.PASS
    assert matches == []


def test_crash_detector_evaluates_warnings() -> None:
    detector = CrashDetector()
    lines = [
        "09-09 10:00:00.000 123 123 W MyApp: Deprecated API called",
    ]
    verdict, matches = detector.evaluate(lines)
    assert verdict == Verdict.PASS_WITH_WARNINGS
    assert len(matches) == 1


@pytest.mark.parametrize(
    "crash_line",
    [
        "09-09 10:00:00.000 123 123 E AndroidRuntime: FATAL EXCEPTION: main",
        "09-09 10:00:00.000 123 123 I ActivityManager: Process com.example.app has died",
        "09-09 10:00:00.000 123 123 E ActivityManager: ANR in com.example.app",
        "09-09 10:00:00.000 123 123 F libc: Fatal signal 11 (SIGSEGV), code 1",
    ],
)
def test_crash_detector_detects_fatal_crashes(crash_line: str) -> None:
    detector = CrashDetector()
    verdict, matches = detector.evaluate([crash_line])
    assert verdict == Verdict.FAIL
    assert len(matches) == 1
    assert matches[0] == crash_line


def test_state_machine_begin_run(tmp_path: Path) -> None:
    sm = TestStateMachine()
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    profile = TestProfile(name="test_prof", observe_timeout_s=5)
    ctx = sm.begin_run(apk_file, "SERIAL123", profile)

    assert sm.context is ctx
    assert ctx.apk_path == apk_file
    assert ctx.device_serial == "SERIAL123"
    assert ctx.observe_timeout_s == 5


def test_state_machine_run_step_without_context_raises() -> None:
    sm = TestStateMachine()
    with pytest.raises(RuntimeError, match="run context is not set"):
        sm.run_step("validate")


def test_state_machine_unknown_step(tmp_path: Path) -> None:
    sm = TestStateMachine()
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")
    sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"))

    with pytest.raises(ValueError, match="Unknown test step"):
        sm.run_step("non_existent_step")


def test_step_validate_success(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy_apk")

    mock_reader = MagicMock()
    mock_reader.inspect_fast.return_value = ApkInfo(
        file_path=apk_file,
        file_hash="hash123",
        package_name="com.test.app",
        version_name="1.0.0",
        version_code=10,
    )
    mock_reader.inspect_full.return_value = mock_reader.inspect_fast.return_value

    sm = TestStateMachine(apk_reader=mock_reader)
    sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"))

    res = sm.run_step("validate")
    assert res.passed is True
    assert "com.test.app" in res.detail
    assert sm.context is not None
    assert sm.context.package_name == "com.test.app"


def test_step_validate_file_not_found(tmp_path: Path) -> None:
    sm = TestStateMachine()
    sm.begin_run(tmp_path / "missing.apk", "SERIAL123", TestProfile(name="default"))

    res = sm.run_step("validate")
    assert res.passed is False
    assert "not found" in res.detail


def test_step_install(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    mock_adb = MagicMock()
    mock_adb.install.return_value = True

    sm = TestStateMachine(adb_client=mock_adb)
    sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"))

    res = sm.run_step("install")
    assert res.passed is True
    mock_adb.install.assert_called_once_with("SERIAL123", apk_file, replace=True, test_ok=True)

    # Test install failure
    mock_adb.install.return_value = False
    res_fail = sm.run_step("install")
    assert res_fail.passed is False


def test_step_launch_success(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    mock_adb = MagicMock()
    mock_adb.launch.return_value = True
    mock_adb.pidof.return_value = 5432

    sm = TestStateMachine(adb_client=mock_adb)
    ctx = sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"))
    ctx.package_name = "com.test.app"

    res = sm.run_step("launch")
    assert res.passed is True
    assert "PID: 5432" in res.detail
    assert ctx.pid == 5432
    mock_adb.logcat_clear.assert_called_once_with("SERIAL123")
    mock_adb.launch.assert_called_once_with("SERIAL123", "com.test.app")


def test_step_launch_failure(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    mock_adb = MagicMock()
    mock_adb.launch.return_value = False

    sm = TestStateMachine(adb_client=mock_adb)
    ctx = sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"))
    ctx.package_name = "com.test.app"

    res = sm.run_step("launch")
    assert res.passed is False
    assert "failed" in res.detail.lower()


def test_step_observe_clean(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    mock_adb = MagicMock()
    mock_adb.logcat_dump.return_value = [
        "09-09 10:00:00.000 123 123 I MyApp: Hello world",
    ]
    mock_adb.pidof.return_value = 123

    sm = TestStateMachine(adb_client=mock_adb)
    ctx = sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default", observe_timeout_s=0))
    ctx.package_name = "com.test.app"
    ctx.pid = 123

    res = sm.run_step("observe")
    assert res.passed is True
    assert "without crashes" in res.detail
    assert ctx.crash_verdict == Verdict.PASS


def test_step_observe_crash(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    mock_adb = MagicMock()
    mock_adb.logcat_dump.return_value = [
        "09-09 10:00:00.000 123 123 E AndroidRuntime: FATAL EXCEPTION: main",
    ]
    mock_adb.pidof.return_value = 123

    sm = TestStateMachine(adb_client=mock_adb)
    ctx = sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default", observe_timeout_s=0))
    ctx.package_name = "com.test.app"
    ctx.pid = 123

    res = sm.run_step("observe")
    assert res.passed is False
    assert "Crash detected" in res.detail
    assert ctx.crash_verdict == Verdict.FAIL


def test_step_screenshot_success(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    mock_adb = MagicMock()
    mock_adb.screenshot.return_value = png_bytes

    out_dir = tmp_path / "shots"
    sm = TestStateMachine(adb_client=mock_adb)
    ctx = sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"), output_dir=out_dir)

    res = sm.run_step("screenshot")
    assert res.passed is True
    assert ctx.screenshot_path is not None
    assert ctx.screenshot_path.is_file()
    assert ctx.screenshot_path.read_bytes() == png_bytes


def test_step_screenshot_invalid(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    mock_adb = MagicMock()
    mock_adb.screenshot.return_value = b"corrupted data"

    sm = TestStateMachine(adb_client=mock_adb)
    sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"))

    res = sm.run_step("screenshot")
    assert res.passed is False
    assert "invalid or empty PNG" in res.detail


def test_step_permissions(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    dumpsys_output = """
    Packages:
      com.test.app:
        runtime permissions:
          android.permission.CAMERA: granted=true, flags=[ ... ]
          android.permission.RECORD_AUDIO: granted=true
          android.permission.INTERNET: granted=false
    """
    mock_adb = MagicMock()
    mock_adb.dumpsys_package.return_value = dumpsys_output

    sm = TestStateMachine(adb_client=mock_adb)
    ctx = sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"))
    ctx.package_name = "com.test.app"

    res = sm.run_step("permissions")
    assert res.passed is True
    assert ctx.granted_permissions == [
        "android.permission.CAMERA",
        "android.permission.RECORD_AUDIO",
    ]
    assert "2 runtime permissions granted" in res.detail


def test_step_network(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    sm = TestStateMachine()
    sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"))

    res = sm.run_step("network")
    assert res.passed is True
    assert "deferred" in res.detail.lower()


def test_step_uninstall(tmp_path: Path) -> None:
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    mock_adb = MagicMock()
    mock_adb.uninstall.return_value = True

    sm = TestStateMachine(adb_client=mock_adb)
    ctx = sm.begin_run(apk_file, "SERIAL123", TestProfile(name="default"))
    ctx.package_name = "com.test.app"

    res = sm.run_step("uninstall")
    assert res.passed is True
    mock_adb.uninstall.assert_called_once_with("SERIAL123", "com.test.app")

    # Test failure
    mock_adb.uninstall.return_value = False
    res_fail = sm.run_step("uninstall")
    assert res_fail.passed is False
