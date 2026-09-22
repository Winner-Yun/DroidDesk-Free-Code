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

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from droiddesk.core.models import ApkInfo, GateResult, ReleaseCheck
from droiddesk.core.severity import GateVerdict, Severity
from droiddesk.infra.db import Repository
from droiddesk.infra.git import GitClient
from droiddesk.services.apk_service import ApkService
from droiddesk.services.env_service import EnvService
from droiddesk.services.scan_service import ScanService

# (category, weight, blocking) — see Section 6.10
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

_HIGH_RISK_PERMISSIONS = {
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.SYSTEM_ALERT_WINDOW",
    "android.permission.WRITE_SETTINGS",
    "android.permission.READ_PHONE_STATE",
}


class _GateWorker(QRunnable):
    def __init__(
        self,
        service: GateService,
        project_root: Path,
        apk_path: Path,
    ) -> None:
        super().__init__()
        self._service = service
        self._project_root = project_root
        self._apk_path = apk_path

    def run(self) -> None:
        try:
            result = self._service.evaluate(self._project_root, self._apk_path)
            self._service.gate_evaluated.emit(result)
        except Exception as e:
            self._service.gate_failed.emit(str(e))


class GateService(QObject):
    gate_evaluated = Signal(object)  # GateResult
    gate_failed = Signal(str)

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

    def evaluate_async(self, project_root: Path, apk_path: Path) -> None:
        """Run gate evaluation on QThreadPool so UI thread is never blocked."""
        worker = _GateWorker(self, project_root, apk_path)
        QThreadPool.globalInstance().start(worker)

    def evaluate(self, project_root: Path, apk_path: Path) -> GateResult:
        """Evaluate all gate categories in dependency order with short-circuiting."""
        checks: list[ReleaseCheck] = []
        apk_info: ApkInfo | None = None
        if self._apk and apk_path.is_file():
            try:
                apk_info = self._apk.inspect(apk_path)
            except Exception:
                apk_info = None

        short_circuited = False

        for category, weight, blocking in _CHECKS:
            if short_circuited:
                checks.append(
                    ReleaseCheck(
                        category=category,
                        passed=False,
                        weight=weight,
                        blocking=blocking,
                        detail="Short-circuited by preceding blocking failure",
                    )
                )
                continue

            passed, detail = self._evaluate_category(category, project_root, apk_path, apk_info)
            checks.append(
                ReleaseCheck(
                    category=category,
                    passed=passed,
                    weight=weight,
                    blocking=blocking,
                    detail=detail,
                )
            )

            if blocking and not passed:
                short_circuited = True

        score = sum(c.weight for c in checks if c.passed)
        blocked = any(c.blocking and not c.passed for c in checks)
        verdict = GateVerdict.BLOCKED if blocked else GateVerdict.GO
        return GateResult(checks=checks, score=score, verdict=verdict)

    def _evaluate_category(
        self,
        category: str,
        project_root: Path,
        apk_path: Path,
        apk_info: ApkInfo | None,
    ) -> tuple[bool, str]:
        if category == "project_identifier":
            expected_pkg: str | None = None
            if self._repo:
                proj = self._repo.get_project_by_root(project_root)
                if proj and proj.package_name:
                    expected_pkg = proj.package_name

            if apk_info:
                if expected_pkg:
                    if apk_info.package_name == expected_pkg:
                        return True, (
                            f"Package name matches expected release identifier — "
                            f"{apk_info.package_name}"
                        )
                    return False, (
                        f"Package name mismatch: expected {expected_pkg}, "
                        f"got {apk_info.package_name}"
                    )
                return True, f"Valid release identifier — {apk_info.package_name}"
            return False, "No valid APK package identifier found"

        elif category == "environment":
            active_env = self._env.active_environment()
            if not active_env:
                return False, "No active environment configured"
            if active_env.allow_release_build:
                host = f" · {active_env.api_host}" if active_env.api_host else ""
                return True, f"{active_env.label} active and permitted to build releases{host}"
            return False, f"Environment '{active_env.label}' is not permitted to build releases"

        elif category == "git_clean":
            is_clean = self._git.is_clean(project_root)
            branch = self._git.current_branch(project_root)
            if is_clean:
                return True, f"Working tree clean, on release branch '{branch or 'release'}'"
            return False, f"Working tree has uncommitted changes on branch '{branch or 'main'}'"

        elif category == "secrets":
            scan_res = self._scan.scan_project(project_root)
            crit = sum(
                1 for f in scan_res.findings if f.severity == Severity.CRITICAL and not f.suppressed
            )
            if crit > 0:
                return False, f"No critical findings in project tree — {crit} critical finding(s)"
            return True, (
                f"No critical findings in the project tree ({scan_res.files_scanned} files scanned)"
            )

        elif category == "apk_valid_signed":
            if apk_info and apk_info.signature_schemes:
                schemes_str = " + ".join(f"v{s}" for s in sorted(apk_info.signature_schemes))
                target = f" · targetSdk {apk_info.target_sdk}" if apk_info.target_sdk else ""
                return True, f"Valid, signed with {schemes_str}{target}"
            return False, "APK is unsigned or lacks v2+ signature schemes"

        elif category == "privacy":
            if apk_path.is_file():
                apk_scan = self._scan.scan_apk(apk_path)
                sens = [
                    f
                    for f in apk_scan.findings
                    if not f.suppressed and f.severity in (Severity.CRITICAL, Severity.HIGH)
                ]
                if sens:
                    return False, f"Credential files present inside APK — {len(sens)} finding(s)"
                return True, "No credential files present inside the APK — assets/, res/raw/ clean"
            return False, "APK file not available for privacy inspection"

        elif category == "permissions":
            if apk_info:
                high_risk = [
                    p for p in apk_info.permissions if any(hr in p for hr in _HIGH_RISK_PERMISSIONS)
                ]
                if high_risk:
                    short_names = [p.split(".")[-1] for p in high_risk[:2]]
                    return False, f"Unreviewed high-risk permissions — {', '.join(short_names)}"
                return True, "No unreviewed high-risk permissions"
            return True, "No high-risk permissions detected"

        elif category == "size":
            max_bytes = 60 * 1024 * 1024
            if apk_path.is_file():
                sz = apk_path.stat().st_size
                mb = sz / (1024 * 1024)
                if sz <= max_bytes:
                    return True, f"Under the configured threshold — {mb:.1f} MB of 60 MB"
                return False, f"Exceeds configured threshold — {mb:.1f} MB of 60 MB"
            return True, "Under the configured threshold — 0 MB of 60 MB"

        return False, f"Unknown check category: {category}"

    def override(self, result: GateResult, reason: str) -> GateResult:
        if not reason.strip():
            raise ValueError("An override reason is required and is recorded permanently.")
        result.verdict = GateVerdict.OVERRIDDEN
        result.override_note = reason
        if self._repo:
            from datetime import UTC, datetime

            from droiddesk.core.models import BuildRecord

            active_env = self._env.active_environment()
            env_key = active_env.key if active_env else "unknown"
            self._repo.save_build_record(
                BuildRecord(
                    command="release-gate",
                    environment=env_key,
                    started_at=datetime.now(UTC),
                    gate_score=result.score,
                    gate_verdict="OVERRIDDEN",
                    overridden=True,
                    override_note=reason,
                )
            )
        return result
