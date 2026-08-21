"""TestService — Section 6.3. The APK Tester state machine: validate, install,
launch, observe, screenshot, permissions, network, uninstall. ApkService.run_test
delegates here.

Crash detection is scoped and specific — never grep for "error", which appears
constantly in normal Android logs. Match FATAL EXCEPTION, `Process <pkg> has died`,
`ANR in <pkg>`, and SIGSEGV, all scoped to the target PID. Everything else is a
warning, surfaced separately from a failure.
"""

from __future__ import annotations

import regex

from droiddesk.core.models import TestStepResult
from droiddesk.core.severity import Verdict

_CRASH_PATTERNS = (
    regex.compile(r"FATAL EXCEPTION"),
    regex.compile(r"Process \S+ has died"),
    regex.compile(r"ANR in \S+"),
    regex.compile(r"signal 11 \(SIGSEGV\)"),
)


class CrashDetector:
    """Evaluates logcat lines already filtered to the target PID (via
    `adb logcat --pid=<pid>`, see Appendix A) and classifies the run.
    """

    def evaluate(self, lines: list[str]) -> tuple[Verdict, list[str]]:
        crashes = [line for line in lines if any(p.search(line) for p in _CRASH_PATTERNS)]
        if crashes:
            return Verdict.FAIL, crashes

        # TODO(Phase 3): classify non-crash anomalies (e.g. repeated warnings) as
        # PASS_WITH_WARNINGS rather than a flat PASS.
        return Verdict.PASS, []


class TestStateMachine:
    """Drives the Validate -> Install -> Launch -> Observe -> Screenshot ->
    Permissions -> Network -> Uninstall sequence defined by a TestProfile,
    reporting each step as a TestStepResult.
    """

    def __init__(self, crash_detector: CrashDetector | None = None) -> None:
        self._crash_detector = crash_detector or CrashDetector()

    def run_step(self, name: str) -> TestStepResult:
        # TODO(Phase 3): one branch per step name, per the command table in
        # Section 6.3 (Appendix A has the exact adb invocations).
        raise NotImplementedError
