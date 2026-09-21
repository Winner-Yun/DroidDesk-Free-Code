from pathlib import Path
from unittest.mock import MagicMock

from droiddesk.core.models import ApkInfo, TestRun, TestStepResult
from droiddesk.core.profiles import TestProfile
from droiddesk.core.severity import Verdict
from droiddesk.services.apk_service import ApkService
from droiddesk.services.test_service import TestRunContext


def test_apk_service_run_test_all_steps_pass(tmp_path: Path) -> None:
    apk_file = tmp_path / "app.apk"
    apk_file.write_bytes(b"dummy_apk")

    mock_reader = MagicMock()
    apk_info = ApkInfo(
        file_path=apk_file,
        file_hash="hash_123",
        package_name="com.example.app",
        version_name="1.0.0",
        version_code=1,
    )
    mock_reader.inspect_fast.return_value = apk_info

    mock_adb = MagicMock()
    mock_sm = MagicMock()

    profile = TestProfile(name="Full smoke")
    ctx = TestRunContext(
        apk_path=apk_file,
        device_serial="DEVICE_1",
        profile=profile,
        package_name="com.example.app",
        apk_info=apk_info,
        log_lines=["Line 1", "Line 2"],
    )
    mock_sm.begin_run.return_value = ctx
    mock_sm.run_step.side_effect = lambda name: TestStepResult(
        name=name, passed=True, duration_ms=10, detail="ok"
    )

    service = ApkService(
        apk_reader=mock_reader,
        adb_client=mock_adb,
        apkanalyzer_path=Path("apkanalyzer"),
        state_machine=mock_sm,
    )

    started_steps: list[str] = []
    finished_steps: list[tuple[str, bool]] = []
    completed_runs: list[TestRun] = []

    service.step_started.connect(started_steps.append)
    service.step_finished.connect(lambda name, passed: finished_steps.append((name, passed)))
    service.test_complete.connect(completed_runs.append)

    run = service.run_test(apk_file, "DEVICE_1", profile)

    assert run.verdict == Verdict.PASS
    assert run.device_serial == "DEVICE_1"
    assert run.profile_name == "Full smoke"
    assert run.apk == apk_info
    assert len(run.steps) == 8
    assert len(started_steps) == 8
    assert len(finished_steps) == 8
    assert len(completed_runs) == 1
    assert completed_runs[0] is run
    assert run.log_excerpt == "Line 1\nLine 2"


def test_apk_service_run_test_step_failure_triggers_cleanup(tmp_path: Path) -> None:
    apk_file = tmp_path / "app.apk"
    apk_file.write_bytes(b"dummy_apk")

    mock_reader = MagicMock()
    apk_info = ApkInfo(
        file_path=apk_file,
        file_hash="hash_123",
        package_name="com.example.app",
    )
    mock_reader.inspect_fast.return_value = apk_info

    mock_adb = MagicMock()
    mock_sm = MagicMock()

    profile = TestProfile(name="Default")
    ctx = TestRunContext(
        apk_path=apk_file,
        device_serial="DEVICE_1",
        profile=profile,
        package_name="com.example.app",
        apk_info=apk_info,
    )
    mock_sm.begin_run.return_value = ctx

    def fake_run_step(name: str) -> TestStepResult:
        if name == "install":
            return TestStepResult(name=name, passed=False, duration_ms=10, detail="INSTALL_FAILED")
        return TestStepResult(name=name, passed=True, duration_ms=10, detail="ok")

    mock_sm.run_step.side_effect = fake_run_step

    service = ApkService(
        apk_reader=mock_reader,
        adb_client=mock_adb,
        apkanalyzer_path=Path("apkanalyzer"),
        state_machine=mock_sm,
    )

    started_steps: list[str] = []
    service.step_started.connect(started_steps.append)

    run = service.run_test(apk_file, "DEVICE_1", profile)

    assert run.verdict == Verdict.FAIL
    # Validate passed, install failed -> launch, observe, screenshot,
    # permissions, and network are skipped -> uninstall runs
    assert started_steps == ["validate", "install", "uninstall"]
    assert len(run.steps) == 3
    assert not run.steps[1].passed
    assert run.steps[2].passed  # uninstall cleanup passed


def test_apk_service_run_test_warnings_verdict(tmp_path: Path) -> None:
    apk_file = tmp_path / "app.apk"
    apk_file.write_bytes(b"dummy_apk")

    mock_reader = MagicMock()
    apk_info = ApkInfo(
        file_path=apk_file,
        file_hash="hash_123",
        package_name="com.example.app",
    )
    mock_reader.inspect_fast.return_value = apk_info

    mock_adb = MagicMock()
    mock_sm = MagicMock()

    profile = TestProfile(name="Default")
    ctx = TestRunContext(
        apk_path=apk_file,
        device_serial="DEVICE_1",
        profile=profile,
        package_name="com.example.app",
        apk_info=apk_info,
        crash_verdict=Verdict.PASS_WITH_WARNINGS,
        crash_lines=["Warning: deprecated method"],
    )
    mock_sm.begin_run.return_value = ctx
    mock_sm.run_step.side_effect = lambda name: TestStepResult(
        name=name, passed=True, duration_ms=10, detail="ok"
    )

    service = ApkService(
        apk_reader=mock_reader,
        adb_client=mock_adb,
        apkanalyzer_path=Path("apkanalyzer"),
        state_machine=mock_sm,
    )

    run = service.run_test(apk_file, "DEVICE_1", profile)

    assert run.verdict == Verdict.PASS_WITH_WARNINGS
    assert run.log_excerpt == "Warning: deprecated method"


def test_apk_service_run_test_disabled_steps(tmp_path: Path) -> None:
    apk_file = tmp_path / "app.apk"
    apk_file.write_bytes(b"dummy_apk")

    mock_reader = MagicMock()
    apk_info = ApkInfo(
        file_path=apk_file,
        file_hash="hash_123",
        package_name="com.example.app",
    )
    mock_reader.inspect_fast.return_value = apk_info

    mock_adb = MagicMock()
    mock_sm = MagicMock()

    # Disable observe, screenshot, permissions, network, uninstall
    profile = TestProfile(
        name="Minimal",
        validate_manifest=True,
        install=True,
        launch=True,
        observe_logcat=False,
        screenshot=False,
        check_permissions=False,
        extract_network_hosts=False,
        uninstall=False,
    )
    ctx = TestRunContext(
        apk_path=apk_file,
        device_serial="DEVICE_1",
        profile=profile,
        package_name="com.example.app",
        apk_info=apk_info,
    )
    mock_sm.begin_run.return_value = ctx
    mock_sm.run_step.side_effect = lambda name: TestStepResult(
        name=name, passed=True, duration_ms=10, detail="ok"
    )

    service = ApkService(
        apk_reader=mock_reader,
        adb_client=mock_adb,
        apkanalyzer_path=Path("apkanalyzer"),
        state_machine=mock_sm,
    )

    started_steps: list[str] = []
    service.step_started.connect(started_steps.append)

    run = service.run_test(apk_file, "DEVICE_1", profile)

    assert run.verdict == Verdict.PASS
    assert started_steps == ["validate", "install", "launch"]
    assert len(run.steps) == 3


def test_apk_service_inspect_delegates(tmp_path: Path) -> None:
    mock_reader = MagicMock()
    mock_adb = MagicMock()

    service = ApkService(
        apk_reader=mock_reader,
        adb_client=mock_adb,
        apkanalyzer_path=Path("apkanalyzer"),
    )

    apk_file = tmp_path / "test.apk"
    service.inspect(apk_file)
    mock_reader.inspect_fast.assert_called_once_with(apk_file)

    service.inspect_full(apk_file)
    mock_reader.inspect_full.assert_called_once_with(apk_file)


def test_apk_service_import_and_local_resilience(tmp_path: Path) -> None:
    from droiddesk.infra.db import Repository

    db_path = tmp_path / "test.db"
    repo = Repository(db_path)
    storage_dir = tmp_path / "storage_apks"

    mock_reader = MagicMock()
    mock_adb = MagicMock()

    # Create original external APK
    external_dir = tmp_path / "downloads"
    external_dir.mkdir()
    original_apk = external_dir / "my_app.apk"
    original_apk.write_bytes(b"apk_binary_data_12345")

    from droiddesk.infra.hashing import hash_file

    expected_hash = hash_file(original_apk)

    def fake_inspect(p: Path) -> ApkInfo:
        return ApkInfo(
            file_path=p,
            file_hash=expected_hash,
            package_name="com.test.myapp",
            version_name="1.0",
            version_code=100,
        )

    mock_reader.inspect_fast.side_effect = fake_inspect

    service = ApkService(
        apk_reader=mock_reader,
        adb_client=mock_adb,
        apkanalyzer_path=Path("apkanalyzer"),
        repository=repo,
        storage_dir=storage_dir,
    )

    # 1. Import APK
    info = service.import_apk(original_apk)
    assert info.file_hash == expected_hash
    assert info.package_name == "com.test.myapp"
    # Local cached copy must exist in storage_dir
    assert info.file_path.is_file()
    assert info.file_path.parent == storage_dir
    assert info.file_path.read_bytes() == b"apk_binary_data_12345"

    # Verify saved in repository
    listed = service.list_apks()
    assert len(listed) == 1
    assert listed[0].file_hash == expected_hash
    assert listed[0].file_path == info.file_path

    # 2. Resilience test: delete the original source file
    original_apk.unlink()
    assert not original_apk.exists()

    # Service can still find and retrieve APK from local storage!
    retrieved = service.get_apk(expected_hash)
    assert retrieved is not None
    assert retrieved.file_path.is_file()
    assert retrieved.file_path.read_bytes() == b"apk_binary_data_12345"

    listed_again = service.list_apks()
    assert len(listed_again) == 1
    assert listed_again[0].file_path.is_file()

    # 3. Removal test
    removed = service.remove_apk(expected_hash)
    assert removed is True
    assert not info.file_path.exists()
    assert service.get_apk(expected_hash) is None
    assert len(service.list_apks()) == 0

    repo.close()
