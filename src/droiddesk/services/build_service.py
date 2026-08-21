"""BuildService (Safe Command Runner) — Section 6.9. Evaluates every guard attached
to a CommandProfile before running it; hard-blocking guards stop execution, warning
guards require an explicit, recorded acknowledgement. Output streams into an
embedded terminal via QProcess (same line-buffered handling as AdbStream), with
ANSI codes parsed into text formatting.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from droiddesk.core.profiles import CommandProfile, GuardResult
from droiddesk.services.env_service import EnvService
from droiddesk.services.scan_service import ScanService


class BuildService(QObject):
    guard_evaluated = Signal(object)  # GuardResult
    output_line = Signal(str)
    command_finished = Signal(int)  # exit code

    def __init__(self, env_service: EnvService, scan_service: ScanService) -> None:
        super().__init__()
        self._env = env_service
        self._scan = scan_service

    def evaluate_guards(self, profile: CommandProfile) -> list[GuardResult]:
        # TODO(Phase 5): one method per guard row in Section 6.9's table
        # (environment_matches, release_allowed, git_clean, secret_scan_clean,
        # no_debug_flags, version_bumped), emitting guard_evaluated for each.
        raise NotImplementedError

    def run(self, profile: CommandProfile, cwd: Path, override_note: str | None = None) -> None:
        guards = self.evaluate_guards(profile)
        blocking_failures = [g for g in guards if g.blocking and not g.passed and not g.overridden]
        if blocking_failures:
            raise RuntimeError(
                f"Blocked by guard(s): {', '.join(g.name for g in blocking_failures)}"
            )
        # TODO(Phase 5): stream `profile.command` via QProcess, parse ANSI codes,
        # emit output_line per flushed chunk, record a build_record row on exit
        # (including override_note when a warning guard was overridden).
        raise NotImplementedError
