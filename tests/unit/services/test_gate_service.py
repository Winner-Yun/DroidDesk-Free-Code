from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from droiddesk.core.models import ApkInfo, GateResult, ScanResult
from droiddesk.core.profiles import Environment
from droiddesk.core.severity import GateVerdict
from droiddesk.infra.db import Repository
from droiddesk.infra.git import GitClient
from droiddesk.services.apk_service import ApkService
from droiddesk.services.env_service import EnvService
from droiddesk.services.gate_service import GateService
from droiddesk.services.scan_service import ScanService


def test_gate_service_evaluate_clean(tmp_path: Path) -> None:
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
    )
    scan_service.scan_apk.return_value = ScanResult(
        target_type="apk",
        target_path=tmp_path / "app.apk",
        started_at=datetime.now(UTC),
        findings=[],
    )

    git_client = MagicMock(spec=GitClient)
    git_client.is_clean.return_value = True

    apk_service = MagicMock(spec=ApkService)
    apk_file = tmp_path / "app.apk"
    apk_file.write_bytes(b"dummy apk content")
    apk_service.inspect.return_value = ApkInfo(
        file_path=apk_file,
        file_hash="fake_hash",
        package_name="com.example.app",
        version_name="1.0.0",
        version_code=1,
        target_sdk=34,
        min_sdk=24,
        size_bytes=len(b"dummy apk content"),
        signature_schemes=[2, 3],
        permissions=["android.permission.INTERNET"],
    )

    service = GateService(
        env_service=env_service,
        scan_service=scan_service,
        git_client=git_client,
        apk_service=apk_service,
    )

    result = service.evaluate(project_root=tmp_path, apk_path=apk_file)

    assert result.verdict == GateVerdict.GO
    assert result.score == 100
    assert len(result.checks) == 8
    assert all(c.passed for c in result.checks)


def test_gate_service_evaluate_short_circuits_on_blocking_failure(tmp_path: Path) -> None:
    env_service = MagicMock(spec=EnvService)
    env_service.project_root = tmp_path
    # Staging has allow_release_build = False -> environment check blocks!
    env_service.active_environment.return_value = Environment(
        key="staging",
        label="Staging",
        env_file=".env.staging",
        allow_release_build=False,
    )

    scan_service = MagicMock(spec=ScanService)
    git_client = MagicMock(spec=GitClient)
    apk_service = MagicMock(spec=ApkService)

    service = GateService(
        env_service=env_service,
        scan_service=scan_service,
        git_client=git_client,
        apk_service=apk_service,
    )

    apk_file = tmp_path / "app.apk"
    apk_file.write_bytes(b"dummy")

    result = service.evaluate(project_root=tmp_path, apk_path=apk_file)

    assert result.verdict == GateVerdict.BLOCKED
    assert result.score < 100
    # Check that environment failed and subsequent blocking checks were short-circuited/skipped
    env_check = next(c for c in result.checks if c.category == "environment")
    assert env_check.passed is False
    assert env_check.blocking is True


def test_gate_service_override(tmp_path: Path) -> None:
    env_service = MagicMock(spec=EnvService)
    scan_service = MagicMock(spec=ScanService)
    repo = MagicMock(spec=Repository)

    service = GateService(
        env_service=env_service,
        scan_service=scan_service,
        repository=repo,
    )

    initial_result = GateResult(
        checks=[],
        score=70,
        verdict=GateVerdict.BLOCKED,
    )

    with pytest.raises(ValueError, match="An override reason is required"):
        service.override(initial_result, "   ")

    overridden = service.override(initial_result, "Approved by Tech Lead for hotfix")
    assert overridden.verdict == GateVerdict.OVERRIDDEN
    assert overridden.override_note == "Approved by Tech Lead for hotfix"
    assert repo.save_build_record.called
