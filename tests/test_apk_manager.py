"""Unit tests for ApkManager error handling and helpers."""

from pathlib import Path

from droiddesk.application.apk_manager import ApkManager
from droiddesk.infra.adb import AdbClient


def test_apk_manager_explain_install_failure() -> None:
    mgr = ApkManager(adb_client=AdbClient(Path("adb.exe")))

    assert "different signature" in mgr._explain_install_failure("INSTALL_FAILED_ALREADY_EXISTS")
    assert "storage space" in mgr._explain_install_failure("INSTALL_FAILED_INSUFFICIENT_STORAGE")
    assert "higher" in mgr._explain_install_failure("INSTALL_FAILED_OLDER_SDK")
    assert "CPU architecture" in mgr._explain_install_failure("INSTALL_FAILED_CPU_ABI_INCOMPATIBLE")
    assert "test-only" in mgr._explain_install_failure("INSTALL_FAILED_TEST_ONLY")
