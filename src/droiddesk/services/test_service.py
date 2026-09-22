"""TestService — Section 6.3. The APK Tester state machine: validate, install,
launch, observe, screenshot, permissions, network, uninstall. ApkService.run_test
delegates here.

Crash detection is scoped and specific — never grep for "error", which appears
constantly in normal Android logs. Match FATAL EXCEPTION, `Process <pkg> has died`,
`ANR in <pkg>`, and SIGSEGV, all scoped to the target PID. Everything else is a
warning, surfaced separately from a failure.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import regex

from droiddesk.core.models import ApkInfo, TestStepResult
from droiddesk.core.profiles import TestProfile
from droiddesk.core.severity import Verdict
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.apk_reader import ApkReader

_CRASH_PATTERNS = (
    regex.compile(r"FATAL EXCEPTION"),
    regex.compile(r"Process \S+ has died"),
    regex.compile(r"ANR in \S+"),
    regex.compile(r"signal 11 \(SIGSEGV\)"),
)

_WARNING_PATTERNS = (
    regex.compile(r"\b(?:WARN|WARNING)\b", regex.IGNORECASE),
    regex.compile(r"\sW\s"),
)


class CrashDetector:
    """Evaluates logcat lines already filtered to the target PID (via
    `adb logcat --pid=<pid>`, see Appendix A) and classifies the run.
    """

    def evaluate(self, lines: list[str]) -> tuple[Verdict, list[str]]:
        crashes = [line for line in lines if any(p.search(line) for p in _CRASH_PATTERNS)]
        if crashes:
            return Verdict.FAIL, crashes

        warnings = [line for line in lines if any(p.search(line) for p in _WARNING_PATTERNS)]
        if warnings:
            return Verdict.PASS_WITH_WARNINGS, warnings

        return Verdict.PASS, []


@dataclass
class TestRunContext:
    """Carries runtime execution context across test steps."""

    __test__ = False

    apk_path: Path
    device_serial: str
    profile: TestProfile
    package_name: str | None = None
    apk_info: ApkInfo | None = None
    pid: int | None = None
    observe_timeout_s: int = 15
    output_dir: Path | None = None
    screenshot_path: Path | None = None
    log_lines: list[str] = field(default_factory=list)
    crash_verdict: Verdict = Verdict.PASS
    crash_lines: list[str] = field(default_factory=list)
    granted_permissions: list[str] = field(default_factory=list)


class TestStateMachine:
    """Drives the Validate -> Install -> Launch -> Observe -> Screenshot ->
    Permissions -> Network -> Uninstall sequence defined by a TestProfile,
    reporting each step as a TestStepResult.
    """

    __test__ = False

    def __init__(
        self,
        adb_client: AdbClient | None = None,
        apk_reader: ApkReader | None = None,
        crash_detector: CrashDetector | None = None,
    ) -> None:
        self._adb = adb_client
        self._reader = apk_reader or ApkReader()
        self._crash_detector = crash_detector or CrashDetector()
        self._context: TestRunContext | None = None

    @property
    def context(self) -> TestRunContext | None:
        return self._context

    def begin_run(
        self,
        apk_path: Path | TestRunContext,
        device_serial: str | None = None,
        profile: TestProfile | None = None,
        output_dir: Path | None = None,
    ) -> TestRunContext:
        """Initializes and returns a TestRunContext for subsequent run_step calls."""
        if isinstance(apk_path, TestRunContext):
            self._context = apk_path
            return self._context

        if device_serial is None or profile is None:
            raise ValueError("device_serial and profile must be provided when apk_path is a Path")

        self._context = TestRunContext(
            apk_path=apk_path,
            device_serial=device_serial,
            profile=profile,
            observe_timeout_s=profile.observe_timeout_s,
            output_dir=output_dir,
        )
        return self._context

    def run_step(self, name: str, context: TestRunContext | None = None) -> TestStepResult:
        """Executes a single test step by name.

        Supported step names:
          - validate / validate_manifest
          - install
          - launch
          - observe / observe_logcat
          - screenshot
          - permissions / check_permissions
          - network / extract_network_hosts
          - uninstall
        """
        if context is not None:
            self._context = context

        if self._context is None:
            raise RuntimeError(
                "TestStateMachine run context is not set. Call begin_run(...) first."
            )

        ctx = self._context
        key = name.strip().lower().replace(" ", "_")

        match key:
            case "validate" | "validate_manifest":
                return self._step_validate(ctx, name)
            case "install":
                return self._step_install(ctx, name)
            case "launch":
                return self._step_launch(ctx, name)
            case "observe" | "observe_logcat":
                return self._step_observe(ctx, name)
            case "screenshot":
                return self._step_screenshot(ctx, name)
            case "permissions" | "check_permissions":
                return self._step_permissions(ctx, name)
            case "network" | "extract_network_hosts":
                return self._step_network(ctx, name)
            case "uninstall" | "clean_up" | "cleanup":
                return self._step_uninstall(ctx, name)
            case _:
                raise ValueError(f"Unknown test step: {name}")

    def _step_validate(self, ctx: TestRunContext, step_name: str) -> TestStepResult:
        t0 = time.perf_counter()
        try:
            if not ctx.apk_path.is_file():
                duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
                return TestStepResult(
                    name=step_name,
                    passed=False,
                    duration_ms=duration_ms,
                    detail=f"APK file not found: {ctx.apk_path}",
                )

            fast_info = self._reader.inspect_fast(ctx.apk_path)
            if not fast_info.package_name:
                duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
                return TestStepResult(
                    name=step_name,
                    passed=False,
                    duration_ms=duration_ms,
                    detail="Manifest did not contain a package name",
                )

            try:
                full_info = self._reader.inspect_full(ctx.apk_path)
                ctx.apk_info = full_info
            except Exception:
                ctx.apk_info = fast_info

            ctx.package_name = ctx.apk_info.package_name
            version_disp = ctx.apk_info.version_name or str(ctx.apk_info.version_code or "unknown")
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return TestStepResult(
                name=step_name,
                passed=True,
                duration_ms=duration_ms,
                detail=f"Package: {ctx.package_name}, Version: {version_disp}",
            )
        except Exception as exc:
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=duration_ms,
                detail=f"Validation failed: {exc}",
            )

    def _step_install(self, ctx: TestRunContext, step_name: str) -> TestStepResult:
        t0 = time.perf_counter()
        if self._adb is None:
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=0,
                detail="AdbClient is not configured",
            )

        try:
            ok = self._adb.install(ctx.device_serial, ctx.apk_path, replace=True, test_ok=True)
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            detail = (
                "APK installed successfully"
                if ok
                else "Installation failed (adb output did not contain Success)"
            )
            return TestStepResult(
                name=step_name,
                passed=ok,
                duration_ms=duration_ms,
                detail=detail,
            )
        except Exception as exc:
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=duration_ms,
                detail=f"Installation error: {exc}",
            )

    def _step_launch(self, ctx: TestRunContext, step_name: str) -> TestStepResult:
        t0 = time.perf_counter()
        if self._adb is None:
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=0,
                detail="AdbClient is not configured",
            )

        try:
            if not ctx.package_name:
                if ctx.apk_info and ctx.apk_info.package_name:
                    ctx.package_name = ctx.apk_info.package_name
                else:
                    info = self._reader.inspect_fast(ctx.apk_path)
                    ctx.apk_info = info
                    ctx.package_name = info.package_name

            if not ctx.package_name:
                duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
                return TestStepResult(
                    name=step_name,
                    passed=False,
                    duration_ms=duration_ms,
                    detail="Cannot launch: package name is unknown",
                )

            # Clear logcat before test per Appendix A
            self._adb.logcat_clear(ctx.device_serial)

            launched = self._adb.launch(ctx.device_serial, ctx.package_name)
            if not launched:
                duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
                return TestStepResult(
                    name=step_name,
                    passed=False,
                    duration_ms=duration_ms,
                    detail=f"Launch command failed for {ctx.package_name}",
                )

            # Poll pidof for process appearance within timeout
            poll_start = time.monotonic()
            poll_timeout = 5.0
            pid: int | None = None
            while time.monotonic() - poll_start < poll_timeout:
                pid = self._adb.pidof(ctx.device_serial, ctx.package_name)
                if pid is not None:
                    break
                time.sleep(0.2)

            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            if pid is not None:
                ctx.pid = pid
                return TestStepResult(
                    name=step_name,
                    passed=True,
                    duration_ms=duration_ms,
                    detail=f"Launched {ctx.package_name} (PID: {pid})",
                )

            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=duration_ms,
                detail=f"Process {ctx.package_name} did not appear in pidof within {poll_timeout}s",
            )
        except Exception as exc:
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=duration_ms,
                detail=f"Launch error: {exc}",
            )

    def _step_observe(self, ctx: TestRunContext, step_name: str) -> TestStepResult:
        t0 = time.perf_counter()
        if self._adb is None:
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=0,
                detail="AdbClient is not configured",
            )

        try:
            timeout_s = max(0, ctx.observe_timeout_s)
            elapsed = 0.0
            step_interval = 0.5

            # Sample logs periodically during observation window
            while elapsed < timeout_s:
                lines = self._adb.logcat_dump(ctx.device_serial, ctx.pid)
                verdict, crash_lines = self._crash_detector.evaluate(lines)
                if verdict == Verdict.FAIL:
                    ctx.log_lines = lines
                    ctx.crash_verdict = verdict
                    ctx.crash_lines = crash_lines
                    duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
                    return TestStepResult(
                        name=step_name,
                        passed=False,
                        duration_ms=duration_ms,
                        detail="Crash detected: " + "; ".join(crash_lines[:3]),
                    )

                # Check if process has died unexpectedly
                if ctx.package_name and ctx.pid is not None:
                    current_pid = self._adb.pidof(ctx.device_serial, ctx.package_name)
                    if current_pid is None or current_pid != ctx.pid:
                        lines = self._adb.logcat_dump(ctx.device_serial, ctx.pid)
                        ctx.log_lines = lines
                        ctx.crash_verdict = Verdict.FAIL
                        ctx.crash_lines = [f"Process {ctx.package_name} (PID {ctx.pid}) died"]
                        duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
                        return TestStepResult(
                            name=step_name,
                            passed=False,
                            duration_ms=duration_ms,
                            detail="Process died unexpectedly during observation",
                        )

                time.sleep(step_interval)
                elapsed += step_interval

            # Final evaluation
            lines = self._adb.logcat_dump(ctx.device_serial, ctx.pid)
            verdict, crash_lines = self._crash_detector.evaluate(lines)
            ctx.log_lines = lines
            ctx.crash_verdict = verdict
            ctx.crash_lines = crash_lines
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))

            if verdict == Verdict.FAIL:
                return TestStepResult(
                    name=step_name,
                    passed=False,
                    duration_ms=duration_ms,
                    detail="Crash detected: " + "; ".join(crash_lines[:3]),
                )
            if verdict == Verdict.PASS_WITH_WARNINGS:
                return TestStepResult(
                    name=step_name,
                    passed=True,
                    duration_ms=duration_ms,
                    detail=f"Observed {len(lines)} logcat lines ({len(crash_lines)} warnings)",
                )

            return TestStepResult(
                name=step_name,
                passed=True,
                duration_ms=duration_ms,
                detail=f"Observed {len(lines)} logcat lines without crashes",
            )
        except Exception as exc:
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=duration_ms,
                detail=f"Observe error: {exc}",
            )

    def _step_screenshot(self, ctx: TestRunContext, step_name: str) -> TestStepResult:
        t0 = time.perf_counter()
        if self._adb is None:
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=0,
                detail="AdbClient is not configured",
            )

        try:
            png_bytes = self._adb.screenshot(ctx.device_serial)
            if len(png_bytes) < 8 or not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
                return TestStepResult(
                    name=step_name,
                    passed=False,
                    duration_ms=duration_ms,
                    detail="Device screenshot returned invalid or empty PNG data",
                )

            shot_dir = ctx.output_dir or (Path(tempfile.gettempdir()) / "droiddesk" / "screenshots")

            shot_dir.mkdir(parents=True, exist_ok=True)
            safe_serial = ctx.device_serial.replace(":", "_").replace("/", "_")
            ts = int(time.time() * 1000)
            shot_path = shot_dir / f"screenshot_{safe_serial}_{ts}.png"
            shot_path.write_bytes(png_bytes)
            ctx.screenshot_path = shot_path

            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return TestStepResult(
                name=step_name,
                passed=True,
                duration_ms=duration_ms,
                detail=str(shot_path),
            )
        except Exception as exc:
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=duration_ms,
                detail=f"Screenshot error: {exc}",
            )

    def _step_permissions(self, ctx: TestRunContext, step_name: str) -> TestStepResult:
        t0 = time.perf_counter()
        if self._adb is None:
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=0,
                detail="AdbClient is not configured",
            )

        try:
            if not ctx.package_name:
                if ctx.apk_info and ctx.apk_info.package_name:
                    ctx.package_name = ctx.apk_info.package_name
                else:
                    info = self._reader.inspect_fast(ctx.apk_path)
                    ctx.apk_info = info
                    ctx.package_name = info.package_name

            if not ctx.package_name:
                duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
                return TestStepResult(
                    name=step_name,
                    passed=False,
                    duration_ms=duration_ms,
                    detail="Cannot inspect permissions: package name is unknown",
                )

            dumpsys_output = self._adb.dumpsys_package(ctx.device_serial, ctx.package_name)
            granted = regex.findall(r"([\w\.]+):\s*granted=true", dumpsys_output)
            ctx.granted_permissions = sorted(set(granted))

            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            detail = f"{len(ctx.granted_permissions)} runtime permissions granted"
            if ctx.apk_info and ctx.apk_info.permissions:
                detail += f" (out of {len(ctx.apk_info.permissions)} declared)"

            return TestStepResult(
                name=step_name,
                passed=True,
                duration_ms=duration_ms,
                detail=detail,
            )
        except Exception as exc:
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=duration_ms,
                detail=f"Permissions inspection error: {exc}",
            )

    def _step_network(self, ctx: TestRunContext, step_name: str) -> TestStepResult:
        t0 = time.perf_counter()
        # Network host extraction depends on Phase 4 string extraction; mark deferred per spec
        duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
        return TestStepResult(
            name=step_name,
            passed=True,
            duration_ms=duration_ms,
            detail="Network host extraction deferred (Phase 4 dependency)",
        )

    def _step_uninstall(self, ctx: TestRunContext, step_name: str) -> TestStepResult:
        t0 = time.perf_counter()
        if self._adb is None:
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=0,
                detail="AdbClient is not configured",
            )

        try:
            if not ctx.package_name:
                if ctx.apk_info and ctx.apk_info.package_name:
                    ctx.package_name = ctx.apk_info.package_name
                else:
                    info = self._reader.inspect_fast(ctx.apk_path)
                    ctx.apk_info = info
                    ctx.package_name = info.package_name

            if not ctx.package_name:
                duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
                return TestStepResult(
                    name=step_name,
                    passed=False,
                    duration_ms=duration_ms,
                    detail="Cannot uninstall: package name is unknown",
                )

            ok = self._adb.uninstall(ctx.device_serial, ctx.package_name)
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            detail = (
                "Package uninstalled successfully"
                if ok
                else "Uninstall failed (adb output did not contain Success)"
            )
            return TestStepResult(
                name=step_name,
                passed=ok,
                duration_ms=duration_ms,
                detail=detail,
            )
        except Exception as exc:
            duration_ms = max(1, int((time.perf_counter() - t0) * 1000))
            return TestStepResult(
                name=step_name,
                passed=False,
                duration_ms=duration_ms,
                detail=f"Uninstall error: {exc}",
            )
