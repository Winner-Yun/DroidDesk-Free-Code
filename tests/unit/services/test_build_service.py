from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from droiddesk.core.models import Finding, ScanResult
from droiddesk.core.profiles import CommandProfile, Environment
from droiddesk.core.severity import Severity
from droiddesk.infra.git import GitClient
from droiddesk.services.build_service import BuildService, strip_ansi
from droiddesk.services.env_service import EnvService
from droiddesk.services.scan_service import ScanService


def test_strip_ansi() -> None:
    raw = "\x1b[31mError: \x1b[0mBuild failed with \x1b[1;33mwarning\x1b[0m"
    assert strip_ansi(raw) == "Error: Build failed with warning"


def test_build_service_guards_clean(tmp_path: Path) -> None:
    env_service = MagicMock(spec=EnvService)
    env_service.project_root = tmp_path
    env_service.active_environment.return_value = Environment(
        key="production",
        label="Production",
        env_file=".env.prod",
        allow_release_build=True,
    )

    scan_service = MagicMock(spec=ScanService)
    scan_service.scan_project.return_value = ScanResult(
        target_type="project",
        target_path=tmp_path,
        started_at=datetime.now(UTC),
        findings=[],
        files_scanned=10,
    )

    git_client = MagicMock(spec=GitClient)
    git_client.is_clean.return_value = True

    service = BuildService(
        env_service=env_service,
        scan_service=scan_service,
        git_client=git_client,
    )

    profile = CommandProfile(
        name="assembleRelease",
        command=["./gradlew", "assembleRelease"],
        required_environment="production",
        guard_environment_matches=True,
        guard_release_allowed=True,
        guard_git_clean=True,
        guard_secret_scan_clean=True,
    )

    results = service.evaluate_guards(profile)
    assert len(results) == 6
    assert all(r.passed for r in results)


def test_build_service_guards_hard_block_critical_secret(tmp_path: Path) -> None:
    env_service = MagicMock(spec=EnvService)
    env_service.project_root = tmp_path
    env_service.active_environment.return_value = Environment(
        key="staging",
        label="Staging",
        env_file=".env.staging",
    )

    scan_service = MagicMock(spec=ScanService)
    scan_service.scan_project.return_value = ScanResult(
        target_type="project",
        target_path=tmp_path,
        started_at=datetime.now(UTC),
        findings=[
            Finding(
                rule_id="aws-access-token",
                severity=Severity.CRITICAL,
                file_path=tmp_path / "secrets.env",
                match_hash="fake_hash",
                redacted="AKIAIOS***",
                line_number=4,
            )
        ],
        files_scanned=5,
    )

    git_client = MagicMock(spec=GitClient)
    git_client.is_clean.return_value = True

    service = BuildService(
        env_service=env_service,
        scan_service=scan_service,
        git_client=git_client,
    )

    profile = CommandProfile(
        name="assembleDebug",
        command=["./gradlew", "assembleDebug"],
        guard_secret_scan_clean=True,
    )

    results = service.evaluate_guards(profile)
    secret_guard = next(g for g in results if g.name == "secret_scan_clean")
    assert secret_guard.passed is False
    assert secret_guard.blocking is True

    # run() must raise RuntimeError on critical secrets even if override_note is provided
    with pytest.raises(RuntimeError, match="CRITICAL secret findings are hard-blocked"):
        service.run(profile, cwd=tmp_path, override_note="Emergency test")
