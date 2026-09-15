from pathlib import Path
from unittest.mock import MagicMock

from droiddesk.infra.adb import AdbClient
from droiddesk.infra.process import ProcessRunner


def test_adb_client_screenshot_binary_safe() -> None:
    mock_runner = MagicMock(spec=ProcessRunner)
    # Raw PNG header and binary bytes containing null bytes and non-ASCII bytes
    png_sample = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x01\x00\x00\x00\x01\x00\x08\x06\x00\x00\x00\xff"
    )
    mock_runner.run_bytes.return_value = png_sample

    adb = AdbClient(adb_path=Path("adb.exe"), runner=mock_runner)
    result = adb.screenshot("SERIAL_123")

    mock_runner.run_bytes.assert_called_once_with(
        Path("adb.exe"),
        ["-s", "SERIAL_123", "exec-out", "screencap", "-p"],
    )
    assert result == png_sample
    assert isinstance(result, bytes)
    assert result.startswith(b"\x89PNG\r\n\x1a\n")


def test_adb_client_install() -> None:
    mock_runner = MagicMock(spec=ProcessRunner)
    mock_res = MagicMock()
    mock_res.stdout = "Performing Streamed Install\nSuccess\n"
    mock_res.exit_code = 0
    mock_runner.run.return_value = mock_res

    adb = AdbClient(adb_path=Path("adb.exe"), runner=mock_runner)
    ok = adb.install("SERIAL_123", Path("sample.apk"))

    assert ok is True
    mock_runner.run.assert_called_once_with(
        Path("adb.exe"),
        ["-s", "SERIAL_123", "install", "-r", "-t", "sample.apk"],
        timeout=120.0,
    )


def test_adb_client_uninstall() -> None:
    mock_runner = MagicMock(spec=ProcessRunner)
    mock_res = MagicMock()
    mock_res.stdout = "Success\n"
    mock_res.exit_code = 0
    mock_runner.run.return_value = mock_res

    adb = AdbClient(adb_path=Path("adb.exe"), runner=mock_runner)
    ok = adb.uninstall("SERIAL_123", "com.example.app")

    assert ok is True
    mock_runner.run.assert_called_once_with(
        Path("adb.exe"),
        ["-s", "SERIAL_123", "uninstall", "com.example.app"],
    )


def test_adb_client_launch_and_pidof() -> None:
    mock_runner = MagicMock(spec=ProcessRunner)
    launch_res = MagicMock()
    launch_res.exit_code = 0
    pidof_res = MagicMock()
    pidof_res.stdout = "4567\n"

    mock_runner.run.side_effect = [launch_res, pidof_res]

    adb = AdbClient(adb_path=Path("adb.exe"), runner=mock_runner)
    launched = adb.launch("SERIAL_123", "com.example.app")
    pid = adb.pidof("SERIAL_123", "com.example.app")

    assert launched is True
    assert pid == 4567


def test_adb_client_logcat_dump() -> None:
    mock_runner = MagicMock(spec=ProcessRunner)
    dump_res = MagicMock()
    dump_res.stdout = (
        "09-09 12:00:00.000 123 123 I Tag: Line 1\n"
        "09-09 12:00:01.000 123 123 I Tag: Line 2\n"
    )
    mock_runner.run.return_value = dump_res

    adb = AdbClient(adb_path=Path("adb.exe"), runner=mock_runner)
    lines = adb.logcat_dump("SERIAL_123", pid=123)

    assert lines == [
        "09-09 12:00:00.000 123 123 I Tag: Line 1",
        "09-09 12:00:01.000 123 123 I Tag: Line 2",
    ]
    mock_runner.run.assert_called_once_with(
        Path("adb.exe"),
        ["-s", "SERIAL_123", "logcat", "-d", "-v", "threadtime", "--pid=123"],
    )
