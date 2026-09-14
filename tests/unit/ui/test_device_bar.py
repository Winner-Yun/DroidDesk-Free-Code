from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from droiddesk.core.models import Device
from droiddesk.services.device_service import DeviceService
from droiddesk.ui.widgets.device_bar import ApkInstallWorker, ApkUploadDialog, DeviceBar
from droiddesk.ui.widgets.environment_bar import EnvironmentBar


def _make_mock_device_service() -> MagicMock:
    service = MagicMock(spec=DeviceService)
    test_device = Device(serial="EMULATOR_1", state="device", model="Pixel 7")
    service.devices.return_value = [test_device]
    devices_signal = MagicMock()
    service.devices_changed = devices_signal
    service.install_apk.return_value = True
    return service


def test_device_bar_initial_state(qapp: QApplication) -> None:
    service = _make_mock_device_service()
    bar = DeviceBar(service)

    assert bar._device_label.text() == "TARGET DEVICE:"
    assert bar.selected_device() is not None
    assert bar.selected_device().serial == "EMULATOR_1"


def test_environment_bar_initial_state(qapp: QApplication) -> None:
    env_bar = EnvironmentBar()

    assert "Upload APK" in env_bar._upload_button.text()
    assert env_bar._apk_selector.count() == 1
    assert env_bar._apk_selector.currentText() == "No APK selected"
    assert env_bar.selected_apk() is None


def test_environment_bar_upload_and_selection(qapp: QApplication, tmp_path: Path) -> None:
    env_bar = EnvironmentBar()

    apk1 = tmp_path / "app1.apk"
    apk2 = tmp_path / "app2.apk"
    apk1.write_text("1")
    apk2.write_text("2")

    selected_apks: list[Path | None] = []
    uploaded_batches: list[list[Path]] = []

    env_bar.apk_selected.connect(lambda p: selected_apks.append(p))
    env_bar.apks_uploaded.connect(lambda b: uploaded_batches.append(b))

    env_bar.add_and_select_apks([apk1, apk2])

    assert env_bar._apk_selector.count() == 2
    assert env_bar.selected_apk() == apk2
    assert len(uploaded_batches) == 1
    assert uploaded_batches[0] == [apk1, apk2]

    # Switch dropdown to first apk
    env_bar._apk_selector.setCurrentIndex(0)
    assert env_bar.selected_apk() == apk1


def test_apk_upload_dialog_table_population(qapp: QApplication, tmp_path: Path) -> None:
    service = _make_mock_device_service()
    apk1 = tmp_path / "app1.apk"
    apk2 = tmp_path / "app2.apk"
    apk1.write_bytes(b"content1" * 100)
    apk2.write_bytes(b"content2" * 200)

    dialog = ApkUploadDialog(
        device_service=service,
        initial_device=service.devices()[0],
        apk_paths=[apk1, apk2],
    )

    assert dialog._table.rowCount() == 2
    assert "app1.apk" in dialog._table.item(0, 0).text()
    assert "app2.apk" in dialog._table.item(1, 0).text()
    assert dialog._table.item(0, 2).text() == "Ready"
    assert dialog._install_btn.isEnabled() is True

    # Test clearing
    dialog._on_clear_clicked()
    assert dialog._table.rowCount() == 0
    assert dialog._install_btn.isEnabled() is False


def test_apk_upload_dialog_install_no_device_alerts(qapp: QApplication, tmp_path: Path) -> None:
    from unittest.mock import patch

    from PySide6.QtWidgets import QMessageBox

    service = _make_mock_device_service()
    service.devices.return_value = []

    apk1 = tmp_path / "app1.apk"
    apk1.write_bytes(b"content1" * 100)

    dialog = ApkUploadDialog(
        device_service=service,
        initial_device=None,
        apk_paths=[apk1],
    )

    assert dialog._dev_selector.selected_device() is None

    with patch.object(QMessageBox, "warning") as mock_warn:
        dialog._on_install_clicked()
        mock_warn.assert_called_once()
        args, _ = mock_warn.call_args
        assert "No Device Connected" in args[1]
        assert "Error: No device connected" in dialog._status_label.text()


def test_apk_install_worker(qapp: QApplication, tmp_path: Path) -> None:
    service = _make_mock_device_service()
    apk1 = tmp_path / "test1.apk"
    apk2 = tmp_path / "test2.apk"
    apk1.write_text("1")
    apk2.write_text("2")

    worker = ApkInstallWorker(
        device_service=service,
        serial="EMULATOR_1",
        apk_paths=[apk1, apk2],
    )

    started: list[Path] = []
    finished: list[tuple[Path, bool]] = []
    summary: list[tuple[int, int]] = []

    worker.apk_started.connect(lambda p: started.append(p))
    worker.apk_finished.connect(lambda p, ok, msg: finished.append((p, ok)))
    worker.all_finished.connect(lambda s, t: summary.append((s, t)))

    worker.run()

    assert len(started) == 2
    assert len(finished) == 2
    assert finished[0] == (apk1, True)
    assert finished[1] == (apk2, True)
    assert summary == [(2, 2)]
    assert service.install_apk.call_count == 2


def test_environment_bar_db_and_settings_persistence(qapp: QApplication, tmp_path: Path) -> None:
    from unittest.mock import patch

    from PySide6.QtWidgets import QMessageBox

    from droiddesk.config import Settings
    from droiddesk.core.models import ApkInfo

    apk1 = tmp_path / "app1.apk"
    apk2 = tmp_path / "app2.apk"
    apk1.write_bytes(b"apk1")
    apk2.write_bytes(b"apk2")

    info1 = ApkInfo(file_path=apk1, file_hash="hash1", package_name="com.app1")
    info2 = ApkInfo(file_path=apk2, file_hash="hash2", package_name="com.app2")

    mock_apk_service = MagicMock()
    mock_apk_service.list_apks.return_value = [info1, info2]
    mock_apk_service.remove_apk.return_value = True

    settings = Settings(config_dir=tmp_path / "cfg", data_dir=tmp_path / "data")
    settings.active_apk_hash = "hash2"

    bar = EnvironmentBar(apk_service=mock_apk_service, settings=settings)

    # Both items should be loaded from the service
    assert bar._apk_selector.count() == 2
    # Active item should match settings.active_apk_hash ("hash2")
    assert bar.selected_apk() == apk2
    assert bar.selected_apk_hash() == "hash2"
    assert bar._remove_button.isEnabled() is True

    # Test removing active APK (hash2)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        bar._on_remove_clicked()

    mock_apk_service.remove_apk.assert_called_once_with("hash2")
    assert bar._apk_selector.count() == 1
    assert bar.selected_apk() == apk1
    assert bar.selected_apk_hash() == "hash1"
    assert settings.active_apk_hash == "hash1"

    # Remove the remaining APK (hash1)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        bar._on_remove_clicked()

    assert bar._apk_selector.count() == 1
    assert bar._apk_selector.itemText(0) == "No APK selected"
    assert bar.selected_apk() is None
    assert bar._remove_button.isEnabled() is False
    assert settings.active_apk_hash is None

