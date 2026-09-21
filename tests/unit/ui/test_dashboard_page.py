from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

from droiddesk.context import AppContext
from droiddesk.core.models import ApkInfo, Device
from droiddesk.ui.pages.dashboard import DashboardPage


def _make_mock_context(tmp_path: Path, devices: list[Device] | None = None) -> AppContext:
    settings = MagicMock()
    settings.data_dir = tmp_path / "data"
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    tool_locator = MagicMock()
    repository = MagicMock()
    repository.list_apks.return_value = []
    repository.list_device_history.return_value = []
    repository.record_device.return_value = None

    device_service = MagicMock()
    if devices is None:
        devices = [
            Device(serial="DEVICE_1", state="device", model="Pixel 7"),
        ]
    device_service._devices = devices
    device_service.devices.return_value = list(devices)
    device_service.devices_changed = MagicMock()

    apk_service = MagicMock()

    return AppContext(
        settings=settings,
        tool_locator=tool_locator,
        repository=repository,
        device_service=device_service,
        apk_service=apk_service,
    )


def test_dashboard_initial_state_and_empty_banner(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = DashboardPage(ctx)

    assert not page._empty_banner.isHidden()
    assert page._apk_card.isHidden()
    assert not hasattr(page, "_switch_project_btn")
    assert not hasattr(page, "_run_gate_btn")
    assert page._stat_devices.value_label.text() == "1"
    assert "connected" in page._stat_devices.caption.text().lower()


def test_dashboard_no_emulator_connected_stat(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path, devices=[])
    page = DashboardPage(ctx)

    assert page._stat_devices.value_label.text() == "0"
    assert "no emulator connected" in page._stat_devices.caption.text().lower()


def test_dashboard_set_apk_displays_card_and_badges(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = DashboardPage(ctx)

    apk_file = tmp_path / "test_app.apk"
    apk_file.write_bytes(b"dummy" * 500)

    apk_info = ApkInfo(
        file_path=apk_file,
        file_hash="hash99",
        package_name="com.test.dashboard",
        version_name="2.1.0",
        version_code=42,
        min_sdk=24,
        target_sdk=34,
        size_bytes=2500,
    )
    ctx.apk_service.inspect = MagicMock(return_value=apk_info)  # type: ignore[method-assign]

    page.set_apk(apk_file)

    assert page._empty_banner.isHidden()
    assert not page._apk_card.isHidden()
    assert page._apk_title_label.text() == "test_app.apk"
    assert page._apk_package_label.text() == "com.test.dashboard"
    assert "v2.1.0" in page._badge_version.text()
    assert "24" in page._badge_min.text()
    assert "34" in page._badge_target.text()

    # Clear APK
    page.set_apk(None)
    assert not page._empty_banner.isHidden()
    assert page._apk_card.isHidden()


def test_dashboard_run_gate_no_apk_shows_alert(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = DashboardPage(ctx)

    with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
        page._on_run_gate_clicked()
        assert mock_warning.called
        assert "No APK Selected" in mock_warning.call_args[0][1]


def test_dashboard_run_gate_with_apk_navigates(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = DashboardPage(ctx)

    apk_file = tmp_path / "app.apk"
    apk_file.write_bytes(b"content")
    page._apk_path = apk_file

    nav_calls: list[str] = []
    page.navigate_requested.connect(nav_calls.append)

    page._on_run_gate_clicked()
    assert nav_calls == ["gate"]


def test_dashboard_run_tests_no_emulator_shows_alert(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path, devices=[])
    page = DashboardPage(ctx)

    with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
        page._on_run_tests_clicked()
        assert mock_warning.called
        assert "No Emulator Connected" in mock_warning.call_args[0][1]


def test_dashboard_run_tests_with_emulator_navigates(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = DashboardPage(ctx)

    nav_calls: list[str] = []
    page.navigate_requested.connect(nav_calls.append)

    page._on_run_tests_clicked()
    assert nav_calls == ["tester"]


def test_dashboard_devices_changed_updates_stat(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path, devices=[])
    page = DashboardPage(ctx)
    assert page._stat_devices.value_label.text() == "0"

    new_devices = [
        Device(serial="EMU_1", state="device"),
        Device(serial="EMU_2", state="device"),
    ]
    ctx.device_service._devices = new_devices
    page._on_devices_changed(new_devices)
    assert page._stat_devices.value_label.text() == "2"
    assert "connected devices" in page._stat_devices.caption.text().lower()


def test_dashboard_apk_installer_alerts_no_apk(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = DashboardPage(ctx)

    with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
        page._on_installer_run_clicked()
        assert mock_warning.called
        assert "No APK Selected" in mock_warning.call_args[0][1]


def test_dashboard_apk_installer_alerts_no_device(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path, devices=[])
    page = DashboardPage(ctx)

    apk_file = tmp_path / "app.apk"
    apk_file.write_bytes(b"dummy")
    page.set_apk(apk_file)

    with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
        page._on_installer_run_clicked()
        assert mock_warning.called
        assert "No Emulator Connected" in mock_warning.call_args[0][1]


def test_dashboard_apk_installer_executes_worker(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = DashboardPage(ctx)

    apk_file = tmp_path / "valid.apk"
    apk_file.write_bytes(b"dummy content")
    page.set_apk(apk_file)

    with patch("droiddesk.ui.pages.dashboard.ApkInstallWorker") as mock_worker_cls:
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = False
        mock_worker_cls.return_value = mock_worker

        page._on_installer_run_clicked()

        mock_worker_cls.assert_called_once()
        mock_worker.start.assert_called_once()
        assert page._installer_run_btn.text() == "Cancel"
        assert not page._installer_progress.isHidden()


def test_dashboard_apk_installer_upload_requested_signal(
    qapp: QApplication, tmp_path: Path
) -> None:
    ctx = _make_mock_context(tmp_path)
    page = DashboardPage(ctx)

    uploaded: list[bool] = []
    page.upload_requested.connect(lambda: uploaded.append(True))

    # Find the "Upload APK" button in the installer card and click it
    found_btn = False
    for btn in page.findChildren(type(page._installer_run_btn)):
        if btn.text() == "Upload APK":
            btn.click()
            found_btn = True
            break
    assert found_btn
    assert uploaded == [True]


def test_dashboard_emulator_history_empty_and_populated(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path, devices=[])
    ctx.repository.list_device_history.return_value = []  # type: ignore[attr-defined]
    page = DashboardPage(ctx)

    assert not page._history_empty_label.isHidden()
    assert page._history_table.isHidden()

    # Now populate history
    ctx.repository.list_device_history.return_value = [  # type: ignore[attr-defined]
        {
            "serial": "DEVICE_1",
            "model": "Pixel 7",
            "state": "device",
            "android_version": "14",
            "api_level": 34,
            "abi": "arm64-v8a",
            "last_connected": "2026-09-15 11:00:00",
        },
        {
            "serial": "OLD_DEVICE",
            "model": "Nexus 5",
            "state": "device",
            "android_version": "6.0",
            "api_level": 23,
            "abi": "armeabi-v7a",
            "last_connected": "2026-09-10 10:00:00",
        },
    ]
    # Active devices has DEVICE_1
    ctx.device_service.devices.return_value = [  # type: ignore[attr-defined]
        Device(serial="DEVICE_1", state="device")
    ]

    page._refresh_emulator_history()

    assert page._history_empty_label.isHidden()
    assert not page._history_table.isHidden()
    assert page._history_table.rowCount() == 2

    # Check cell items
    item_0_1 = page._history_table.item(0, 1)
    assert item_0_1 is not None and "Pixel 7" in item_0_1.text()
    item_0_2 = page._history_table.item(0, 2)
    assert item_0_2 is not None and "Android 14 (API 34)" in item_0_2.text()

    # Check auto-recording on devices changed
    new_dev = Device(serial="EMU_99", state="device", model="Tablet")
    page._on_devices_changed([new_dev])
    ctx.repository.record_device.assert_called()  # type: ignore[attr-defined]
