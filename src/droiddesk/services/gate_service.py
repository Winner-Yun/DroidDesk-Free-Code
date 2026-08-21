"""GateService (Release Gate) — Section 6.10. Composes every other check into a
single scored, categorical verdict. Runs checks in dependency order, short-
circuiting on the first hard (blocking) failure. The score tracks improvement over
time; the verdict is what actually governs the build.

Override policy: a blocking check can only be bypassed through a dialog that
requires typing a reason, permanently recorded in build_record. Visible-but-possible
beats impossible — making it impossible just drives people around the tool.
"""

from __future__ import annotations

from pathlib import Path

from droiddesk.core.models import GateResult, ReleaseCheck
from droiddesk.core.severity import GateVerdict

# (category, weight, blocking) — see the table in Section 6.10.
_CHECKS: tuple[tuple[str, int, bool], ...] = (
    ("project_identifier", 10, True),
    ("environment", 20, True),
    ("git_clean", 10, False),
    ("secrets", 20, True),
    ("apk_valid_signed", 15, True),
    ("privacy", 15, True),
    ("permissions", 5, False),
    ("size", 5, False),
)


class GateService:
    def evaluate(self, project_root: Path, apk_path: Path) -> GateResult:
        checks: list[ReleaseCheck] = []
        for category, weight, blocking in _CHECKS:
            # TODO(Phase 5): one evaluator per category, delegating to EnvService,
            # ScanService, ApkService as appropriate. Short-circuit remaining
            # checks once a blocking failure is hit.
            raise NotImplementedError

        score = sum(c.weight for c in checks if c.passed)
        blocked = any(c.blocking and not c.passed for c in checks)
        verdict = GateVerdict.BLOCKED if blocked else GateVerdict.GO
        return GateResult(checks=checks, score=score, verdict=verdict)

    def override(self, result: GateResult, reason: str) -> GateResult:
        if not reason.strip():
            raise ValueError("An override reason is required and is recorded permanently.")
        result.verdict = GateVerdict.OVERRIDDEN
        result.override_note = reason
        return result
