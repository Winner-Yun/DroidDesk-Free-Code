"""ApkService — Section 6.2 and Section 4.3 (the APK Test Run data flow). Orchestrates
ApkReader, AdbClient, and the test state machine (TestService). Owns no widgets;
progress and completion surface via Qt signals.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from droiddesk.core.models import ApkInfo, TestRun, TestStepResult
from droiddesk.core.profiles import TestProfile
from droiddesk.core.severity import Verdict
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.apk_reader import ApkReader
from droiddesk.services.test_service import CrashDetector, TestStateMachine


class ApkService(QObject):
    step_started = Signal(str)
    step_finished = Signal(str, bool)  # step name, passed
    test_complete = Signal(object)  # TestRun

    def __init__(
        self,
        apk_reader: ApkReader,
        adb_client: AdbClient,
        apkanalyzer_path: Path,
        state_machine: TestStateMachine | None = None,
        crash_detector: CrashDetector | None = None,
    ) -> None:
        super().__init__()
        self._reader = apk_reader
        self._adb = adb_client
        self._apkanalyzer_path = apkanalyzer_path
        self._crash_detector = crash_detector or CrashDetector()
        self._state_machine = state_machine or TestStateMachine(
            adb_client=self._adb,
            apk_reader=self._reader,
            crash_detector=self._crash_detector,
        )

    def inspect(self, apk_path: Path) -> ApkInfo:
        return self._reader.inspect_fast(apk_path)

    def inspect_full(self, apk_path: Path) -> ApkInfo:
        return self._reader.inspect_full(apk_path)

    def compare(self, apk_a: Path, apk_b: Path) -> dict[str, object]:
        from droiddesk.infra.process import ProcessRunner
        runner = ProcessRunner()
        result = runner.run(
            self._apkanalyzer_path,
            ["apk", "compare", str(apk_a), str(apk_b)],
        )
        return {"output": result.stdout, "exit_code": result.exit_code}

    def run_test(
        self,
        apk_path: Path,
        device_serial: str,
        profile: TestProfile,
        output_dir: Path | None = None,
    ) -> TestRun:
        started_at = datetime.now(UTC)
        t0 = time.perf_counter()

        ctx = self._state_machine.begin_run(
            apk_path=apk_path,
            device_serial=device_serial,
            profile=profile,
            output_dir=output_dir,
        )

        steps: list[TestStepResult] = []

        sequence: list[tuple[str, bool]] = [
            ("validate", profile.validate_manifest),
            ("install", profile.install),
            ("launch", profile.launch),
            ("observe", profile.observe_logcat),
            ("screenshot", profile.screenshot),
            ("permissions", profile.check_permissions),
            ("network", profile.extract_network_hosts),
        ]

        critical_failure = False

        for step_name, enabled in sequence:
            if not enabled:
                continue

            if critical_failure:
                break

            self.step_started.emit(step_name)
            step_result = self._state_machine.run_step(step_name)
            steps.append(step_result)
            self.step_finished.emit(step_name, step_result.passed)

            if not step_result.passed and step_name in ("validate", "install", "launch"):
                critical_failure = True

        # Always attempt cleanup if enabled in the profile
        if profile.uninstall:
            self.step_started.emit("uninstall")
            uninstall_result = self._state_machine.run_step("uninstall")
            steps.append(uninstall_result)
            self.step_finished.emit("uninstall", uninstall_result.passed)

        duration_ms = max(1, int((time.perf_counter() - t0) * 1000))

        if any(not s.passed for s in steps):
            verdict = Verdict.FAIL
        elif ctx.crash_verdict == Verdict.PASS_WITH_WARNINGS:
            verdict = Verdict.PASS_WITH_WARNINGS
        else:
            verdict = Verdict.PASS

        if ctx.crash_lines:
            log_excerpt: str | None = "\n".join(ctx.crash_lines)
        elif ctx.log_lines:
            log_excerpt = "\n".join(ctx.log_lines[-50:])
        else:
            log_excerpt = None

        apk_info = ctx.apk_info
        if apk_info is None:
            try:
                apk_info = self._reader.inspect_fast(apk_path)
            except Exception:
                apk_info = ApkInfo(
                    file_path=apk_path,
                    file_hash="",
                    package_name=ctx.package_name or "unknown",
                )

        run = TestRun(
            apk=apk_info,
            device_serial=device_serial,
            profile_name=profile.name,
            started_at=started_at,
            steps=steps,
            verdict=verdict,
            duration_ms=duration_ms,
            log_excerpt=log_excerpt,
            screenshot_path=ctx.screenshot_path,
        )

        self.test_complete.emit(run)
        return run
