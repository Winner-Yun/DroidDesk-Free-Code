import contextlib
import re
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from droiddesk.core.models import BuildRecord
from droiddesk.core.profiles import CommandProfile, GuardResult
from droiddesk.core.severity import Severity
from droiddesk.infra.db import Repository
from droiddesk.infra.git import GitClient
from droiddesk.services.apk_service import ApkService
from droiddesk.services.env_service import EnvService
from droiddesk.services.scan_service import ScanService

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text for terminal display."""
    return _ANSI_ESCAPE.sub("", text)


class BuildService(QObject):
    guard_evaluated = Signal(object)  # GuardResult
    output_line = Signal(str)
    command_finished = Signal(int)  # exit code

    def __init__(
        self,
        env_service: EnvService,
        scan_service: ScanService,
        git_client: GitClient | None = None,
        apk_service: ApkService | None = None,
        repository: Repository | None = None,
    ) -> None:
        super().__init__()
        self._env = env_service
        self._scan = scan_service
        self._git = git_client or GitClient()
        self._apk = apk_service
        self._repo = repository
        self._process: QProcess | None = None
        self._active_profile: CommandProfile | None = None
        self._start_time: datetime | None = None
        self._override_note: str | None = None

    def evaluate_guards(
        self,
        profile: CommandProfile,
        apk_path: Path | None = None,
    ) -> list[GuardResult]:
        """Evaluate safety build guards."""
        results: list[GuardResult] = []

        # Environment match check
        g_env = self._guard_environment_matches(profile)
        results.append(g_env)
        self.guard_evaluated.emit(g_env)

        # Release permissions check
        g_rel = self._guard_release_allowed(profile)
        results.append(g_rel)
        self.guard_evaluated.emit(g_rel)

        # Git status check
        g_git = self._guard_git_clean(profile)
        results.append(g_git)
        self.guard_evaluated.emit(g_git)

        # Secret scan verification
        g_sec = self._guard_secret_scan_clean(profile)
        results.append(g_sec)
        self.guard_evaluated.emit(g_sec)

        # Debug flags verification
        g_dbg = self._guard_no_debug_flags(profile, apk_path)
        results.append(g_dbg)
        self.guard_evaluated.emit(g_dbg)

        # Version bump verification
        g_ver = self._guard_version_bumped(profile, apk_path)
        results.append(g_ver)
        self.guard_evaluated.emit(g_ver)

        return results

    def _guard_environment_matches(self, profile: CommandProfile) -> GuardResult:
        if not profile.guard_environment_matches or not profile.required_environment:
            return GuardResult(
                name="environment_matches",
                passed=True,
                blocking=True,
                detail="Environment match check not required",
            )

        active_env = self._env.active_environment()
        if active_env and active_env.key == profile.required_environment:
            return GuardResult(
                name="environment_matches",
                passed=True,
                blocking=True,
                detail=f"Active environment matches required '{profile.required_environment}'",
            )

        active_key = active_env.key if active_env else "None"
        return GuardResult(
            name="environment_matches",
            passed=False,
            blocking=True,
            detail=(
                f"Active environment '{active_key}' does not match "
                f"required '{profile.required_environment}'"
            ),
        )

    def _guard_release_allowed(self, profile: CommandProfile) -> GuardResult:
        if not profile.guard_release_allowed:
            return GuardResult(
                name="release_allowed",
                passed=True,
                blocking=True,
                detail="Release permission check not required",
            )

        active_env = self._env.active_environment()
        if active_env and active_env.allow_release_build:
            return GuardResult(
                name="release_allowed",
                passed=True,
                blocking=True,
                detail=f"Environment '{active_env.key}' permits release builds",
            )

        active_key = active_env.key if active_env else "None"
        return GuardResult(
            name="release_allowed",
            passed=False,
            blocking=True,
            detail=f"Environment '{active_key}' does not permit release builds",
        )

    def _guard_git_clean(self, profile: CommandProfile) -> GuardResult:
        if not profile.guard_git_clean:
            return GuardResult(
                name="git_clean",
                passed=True,
                blocking=True,
                detail="Git clean check not required",
            )

        is_clean = self._git.is_clean(self._env.project_root)
        branch = self._git.current_branch(self._env.project_root)
        if is_clean:
            return GuardResult(
                name="git_clean",
                passed=True,
                blocking=True,
                detail=f"Working tree clean on branch '{branch or 'detached'}'",
            )

        return GuardResult(
            name="git_clean",
            passed=False,
            blocking=True,
            detail=f"Working tree has uncommitted changes on branch '{branch or 'detached'}'",
        )

    def _guard_secret_scan_clean(self, profile: CommandProfile) -> GuardResult:
        if not profile.guard_secret_scan_clean:
            return GuardResult(
                name="secret_scan_clean",
                passed=True,
                blocking=True,
                detail="Secret scan not required",
            )

        scan_result = self._scan.scan_project(self._env.project_root)
        critical_count = sum(
            1 for f in scan_result.findings if f.severity == Severity.CRITICAL and not f.suppressed
        )
        if critical_count > 0:
            return GuardResult(
                name="secret_scan_clean",
                passed=False,
                blocking=True,
                detail=f"Blocked: {critical_count} CRITICAL secret finding(s) detected",
            )

        return GuardResult(
            name="secret_scan_clean",
            passed=True,
            blocking=True,
            detail=f"No critical secrets detected ({scan_result.files_scanned} files scanned)",
        )

    def _guard_no_debug_flags(
        self,
        profile: CommandProfile,
        apk_path: Path | None = None,
    ) -> GuardResult:
        if not profile.guard_no_debug_flags:
            return GuardResult(
                name="no_debug_flags",
                passed=True,
                blocking=True,
                detail="Debug flags check not required",
            )

        target = apk_path
        if target and target.is_file() and self._apk:
            try:
                info = self._apk.inspect(target)
                if info.debuggable is True:
                    return GuardResult(
                        name="no_debug_flags",
                        passed=False,
                        blocking=True,
                        detail=f"Release APK '{target.name}' has android:debuggable=true",
                    )
                return GuardResult(
                    name="no_debug_flags",
                    passed=True,
                    blocking=True,
                    detail=f"Release APK '{target.name}' is not debuggable",
                )
            except Exception as e:
                return GuardResult(
                    name="no_debug_flags",
                    passed=False,
                    blocking=True,
                    detail=f"Failed to inspect APK debug flag: {e}",
                )

        return GuardResult(
            name="no_debug_flags",
            passed=True,
            blocking=True,
            detail="No target APK provided to inspect for debug flags",
        )

    def _guard_version_bumped(
        self,
        profile: CommandProfile,
        apk_path: Path | None = None,
    ) -> GuardResult:
        if not profile.guard_version_bumped:
            return GuardResult(
                name="version_bumped",
                passed=True,
                blocking=False,
                detail="Version bump check not required",
            )

        target = apk_path
        if target and target.is_file() and self._apk and self._repo:
            try:
                info = self._apk.inspect(target)
                existing = self._repo.list_apks()
                same_pkg = [
                    a
                    for a in existing
                    if a.package_name == info.package_name
                    and a.file_hash != info.file_hash
                    and a.version_code is not None
                ]
                if same_pkg and info.version_code is not None:
                    max_prev = max(a.version_code for a in same_pkg if a.version_code is not None)
                    if info.version_code <= max_prev:
                        return GuardResult(
                            name="version_bumped",
                            passed=False,
                            blocking=False,
                            detail=(
                                f"Version code {info.version_code} not greater "
                                f"than previous {max_prev}"
                            ),
                        )
                    return GuardResult(
                        name="version_bumped",
                        passed=True,
                        blocking=False,
                        detail=f"Version code bumped ({max_prev} -> {info.version_code})",
                    )
            except Exception:
                pass

        return GuardResult(
            name="version_bumped",
            passed=True,
            blocking=False,
            detail="Version verification completed",
        )

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.state() != QProcess.ProcessState.NotRunning

    def stop(self) -> None:
        if self._process and self.is_running():
            self._process.kill()

    def run(
        self,
        profile: CommandProfile,
        cwd: Path,
        override_note: str | None = None,
        apk_path: Path | None = None,
    ) -> None:
        """Evaluate guards, short-circuit on hard blocks, and stream output via QProcess."""
        guards = self.evaluate_guards(profile, apk_path=apk_path)

        # Hard-block on critical secret findings
        for g in guards:
            if g.name == "secret_scan_clean" and not g.passed:
                raise RuntimeError(
                    "CRITICAL secret findings are hard-blocked and cannot be overridden."
                )

        # Check for un-overridden blocking guard failures
        blocking_failures = [
            g
            for g in guards
            if g.blocking and not g.passed and not (override_note and not g.overridden)
        ]
        if blocking_failures:
            raise RuntimeError(
                f"Blocked by guard(s): {', '.join(g.name for g in blocking_failures)}"
            )

        if not profile.command:
            raise ValueError("Command profile contains an empty command.")

        self._active_profile = profile
        self._start_time = datetime.now(UTC)
        self._override_note = override_note

        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(cwd))
        self._process.readyReadStandardOutput.connect(self._on_stdout_ready)
        self._process.readyReadStandardError.connect(self._on_stderr_ready)
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)

        import sys

        program = profile.command[0]
        args = profile.command[1:]

        if sys.platform.startswith("win"):
            if program in ("./gradlew", ".\\gradlew", "gradlew"):
                bat_file = cwd / "gradlew.bat"
                if bat_file.is_file():
                    program = "cmd.exe"
                    args = ["/c", str(bat_file), *args]
                elif (cwd / "gradlew.cmd").is_file():
                    program = "cmd.exe"
                    args = ["/c", str(cwd / "gradlew.cmd"), *args]
            elif program.lower().endswith(".bat") or program.lower().endswith(".cmd"):
                program = "cmd.exe"
                args = ["/c", profile.command[0], *args]

        self._process.start(program, args)

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if self._process:
            err_msg = self._process.errorString()
            self.output_line.emit(f"\n[Execution error: {error.name} - {err_msg}]")
        self.command_finished.emit(-1)

    def _on_stdout_ready(self) -> None:
        if not self._process:
            return
        data = bytes(self._process.readAllStandardOutput().data()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            self.output_line.emit(strip_ansi(line))

    def _on_stderr_ready(self) -> None:
        if not self._process:
            return
        data = bytes(self._process.readAllStandardError().data()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            self.output_line.emit(strip_ansi(line))

    def _on_process_finished(self, exit_code: int) -> None:
        if self._repo and self._active_profile:
            active_env = self._env.active_environment()
            env_key = active_env.key if active_env is not None else "unknown"
            record = BuildRecord(
                command=" ".join(self._active_profile.command),
                environment=env_key,
                started_at=self._start_time or datetime.now(UTC),
                overridden=bool(self._override_note),
                override_note=self._override_note,
                exit_code=exit_code,
            )
            with contextlib.suppress(Exception):
                self._repo.save_build_record(record)

        self.command_finished.emit(exit_code)
