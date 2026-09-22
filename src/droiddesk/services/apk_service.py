"""ApkService — Section 6.2 and Section 4.3 (the APK Test Run data flow). Orchestrates
ApkReader, AdbClient, and the test state machine (TestService). Owns no widgets;
progress and completion surface via Qt signals.
"""

from __future__ import annotations

import contextlib
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from droiddesk.core.models import ApkInfo, TestRun, TestStepResult
from droiddesk.core.profiles import TestProfile
from droiddesk.core.severity import Verdict
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.apk_reader import ApkReader
from droiddesk.infra.db import Repository
from droiddesk.infra.hashing import hash_file
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
        repository: Repository | None = None,
        storage_dir: Path | None = None,
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
        self._repository = repository
        self._storage_dir = storage_dir
        if self._storage_dir:
            self._storage_dir.mkdir(parents=True, exist_ok=True)

    def import_apk(self, source_path: Path) -> ApkInfo:
        """Import an APK into project storage and persist its metadata to the database.

        The APK file is copied into the local storage directory so it remains available
        even if the source file is deleted or moved.
        """
        if not source_path.is_file():
            raise FileNotFoundError(f"APK file not found: {source_path}")

        file_hash = hash_file(source_path)

        if self._storage_dir:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            target_name = f"{file_hash[:12]}_{source_path.name}"
            target_path = self._storage_dir / target_name
            same_file = source_path.resolve() == target_path.resolve()
            if not same_file and (
                not target_path.is_file()
                or target_path.stat().st_size != source_path.stat().st_size
            ):
                shutil.copy2(source_path, target_path)
            working_path = target_path
        else:
            working_path = source_path

        info = self._reader.inspect_fast(working_path)
        info.file_path = working_path
        info.file_hash = file_hash

        if self._repository:
            self._repository.save_apk(info)

        return info

    def list_apks(self) -> list[ApkInfo]:
        """List all project APKs from the database, resolving paths against local storage."""
        if not self._repository:
            return []

        apks = self._repository.list_apks()

        for apk in apks:
            updated = False
            # Check if current path exists
            if not apk.file_path.is_file() and self._storage_dir:
                candidate = self._storage_dir / f"{apk.file_hash[:12]}_{apk.file_path.name}"
                if candidate.is_file():
                    apk.file_path = candidate
                    updated = True
                else:
                    matches = list(self._storage_dir.glob(f"{apk.file_hash[:12]}_*"))
                    if matches and matches[0].is_file():
                        apk.file_path = matches[0]
                        updated = True
            elif apk.file_path.is_file() and self._storage_dir:
                resolved_storage = self._storage_dir.resolve()
                try:
                    is_in_storage = apk.file_path.resolve().is_relative_to(resolved_storage)
                except Exception:
                    is_in_storage = False

                if not is_in_storage:
                    target_name = f"{apk.file_hash[:12]}_{apk.file_path.name}"
                    target_path = self._storage_dir / target_name
                    if not target_path.is_file():
                        with contextlib.suppress(Exception):
                            shutil.copy2(apk.file_path, target_path)
                            apk.file_path = target_path
                            updated = True

            if updated and self._repository:
                self._repository.save_apk(apk)

        return apks

    def get_apk(self, file_hash: str) -> ApkInfo | None:
        """Retrieve an APK by its hash from the database."""
        if not self._repository:
            return None
        apk = self._repository.get_apk_by_hash(file_hash)
        if apk and not apk.file_path.is_file() and self._storage_dir:
            candidate = self._storage_dir / f"{apk.file_hash[:12]}_{apk.file_path.name}"
            if candidate.is_file():
                apk.file_path = candidate
                self._repository.save_apk(apk)
            else:
                matches = list(self._storage_dir.glob(f"{apk.file_hash[:12]}_*"))
                if matches and matches[0].is_file():
                    apk.file_path = matches[0]
                    self._repository.save_apk(apk)
        return apk

    def remove_apk(self, file_hash: str) -> bool:
        """Remove an APK from the database and delete its cached copy from local storage."""
        if not self._repository:
            return False

        apk = self._repository.get_apk_by_hash(file_hash)
        deleted = self._repository.delete_apk(file_hash)

        # Remove local cached copy in storage_dir if present
        if self._storage_dir and self._storage_dir.is_dir():
            for cached_file in self._storage_dir.glob(f"{file_hash[:12]}_*"):
                with contextlib.suppress(Exception):
                    cached_file.unlink(missing_ok=True)

        if apk and self._storage_dir:
            with contextlib.suppress(Exception):
                resolved_storage = self._storage_dir.resolve()
                if apk.file_path.resolve().is_relative_to(resolved_storage):
                    apk.file_path.unlink(missing_ok=True)

        return deleted

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
