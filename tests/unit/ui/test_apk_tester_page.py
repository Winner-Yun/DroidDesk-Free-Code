from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from droiddesk.context import AppContext
from droiddesk.core.models import ApkInfo, Device, TestRun, TestStepResult
from droiddesk.core.severity import Verdict
from droiddesk.ui.pages.apk_tester import ApkTesterPage


def _make_mock_context(tmp_path: Path) -> AppContext:
    settings = MagicMock()
    settings.data_dir = tmp_path / "data"
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    tool_locator = MagicMock()
    repository = MagicMock()

    device_service = MagicMock()
    device_service._devices = [
        Device(serial="DEVICE_1", state="device", model="Pixel 7"),
    ]
    # Mock devices_changed signal
    devices_signal = MagicMock()
    device_service.devices_changed = devices_signal

    apk_service = MagicMock()
    # Mock signals
    apk_service.step_started = MagicMock()
    apk_service.step_finished = MagicMock()
    apk_service.test_complete = MagicMock()

    return AppContext(
        settings=settings,
        tool_locator=tool_locator,
        repository=repository,
        device_service=device_service,
        apk_service=apk_service,
    )


def test_apk_tester_page_initial_state(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = ApkTesterPage(ctx)

    assert len(page._step_widgets) == 8
    assert "validate" in page._step_widgets
    assert "install" in page._step_widgets
    assert "uninstall" in page._step_widgets

    assert page._apk_name_label.text() == "No APK selected"
    assert page._verdict_label.text() == "PENDING"
    assert page._run_button.isEnabled() is True
    assert page._open_report.isEnabled() is False


def test_apk_tester_page_on_apk_selected(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"dummy")

    apk_info = ApkInfo(
        file_path=apk_file,
        file_hash="hash123",
        package_name="com.test.live",
        version_name="3.2.1",
        version_code=100,
        min_sdk=24,
        target_sdk=34,
    )
    ctx.apk_service.inspect.return_value = apk_info

    page = ApkTesterPage(ctx)
    page._on_apk_selected(apk_file)

    assert page._apk_name_label.text() == "test.apk"
    assert page._apk_package_label.text() == "com.test.live"
    assert "3.2.1" in page._tag_version.text()
    assert "min 24" in page._tag_min.text()
    assert "target 34" in page._tag_target.text()


def test_apk_tester_page_step_signals_update_widgets(
    qapp: QApplication, tmp_path: Path
) -> None:
    ctx = _make_mock_context(tmp_path)
    page = ApkTesterPage(ctx)

    validate_widget = page._step_widgets["validate"]
    assert validate_widget.headline_label.text() == "Pending"

    page._on_step_started("validate")
    assert validate_widget.headline_label.text() == "Running..."
    assert validate_widget.icon_label.text() == "▶"

    page._on_step_finished("validate", True)
    assert validate_widget.headline_label.text() == "Success"
    assert validate_widget.icon_label.text() == "✓"

    install_widget = page._step_widgets["install"]
    page._on_step_started("install")
    assert install_widget.headline_label.text() == "Running..."

    page._on_step_finished("install", False)
    assert install_widget.headline_label.text() == "Failed"
    assert install_widget.icon_label.text() == "✕"


def test_apk_tester_page_on_test_complete(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = ApkTesterPage(ctx)

    apk_info = ApkInfo(
        file_path=tmp_path / "app.apk",
        file_hash="h1",
        package_name="com.test.app",
    )
    run = TestRun(
        apk=apk_info,
        device_serial="DEVICE_1",
        profile_name="Default",
        started_at=datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC),
        steps=[
            TestStepResult("validate", True, 45, "Package: com.test.app"),
            TestStepResult("install", True, 1200, "APK installed successfully"),
            TestStepResult("uninstall", True, 400, "Package uninstalled successfully"),
        ],
        verdict=Verdict.PASS,
        duration_ms=1645,
        log_excerpt="Sample logs",
    )

    page._on_test_complete(run)

    assert page._verdict_label.text() == "PASS"
    assert "Completed all steps in 1645 ms" in page._verdict_detail.text()
    assert page._run_button.isEnabled() is True
    assert page._open_report.isEnabled() is True
    assert page._step_widgets["validate"].duration_label.text() == "45 ms"
    assert page._log_excerpt_view.toPlainText() == "Sample logs"
