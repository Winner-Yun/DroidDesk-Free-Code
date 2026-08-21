"""ApkService — Section 6.2 and Section 4.3 (the APK Test Run data flow). Orchestrates
ApkReader, AdbClient, and the test state machine (TestService). Owns no widgets;
progress and completion surface via Qt signals.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from droiddesk.core.models import ApkInfo, TestRun
from droiddesk.core.profiles import TestProfile
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.apk_reader import ApkReader


class ApkService(QObject):
    step_started = Signal(str)
    step_finished = Signal(str, bool)  # step name, passed
    test_complete = Signal(object)  # TestRun

    def __init__(self, apk_reader: ApkReader, adb_client: AdbClient) -> None:
        super().__init__()
        self._reader = apk_reader
        self._adb = adb_client

    def inspect(self, apk_path: Path) -> ApkInfo:
        return self._reader.inspect_fast(apk_path)

    def compare(self, apk_a: Path, apk_b: Path) -> dict[str, object]:
        # TODO(Phase 2): apkanalyzer apk compare + manifest diff.
        raise NotImplementedError

    def run_test(self, apk_path: Path, device_serial: str, profile: TestProfile) -> TestRun:
        # TODO(Phase 3): drive the state machine described in Section 4.3 —
        # validate -> install -> launch -> observe (logcat + screenshot in
        # parallel) -> crash detection -> uninstall, emitting step_started /
        # step_finished throughout, then test_complete with the assembled TestRun.
        raise NotImplementedError
