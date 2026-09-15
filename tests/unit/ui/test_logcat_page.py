from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QPushButton

from droiddesk.context import AppContext
from droiddesk.core.models import Device
from droiddesk.ui.pages.devices import DevicesPage
from droiddesk.ui.pages.logcat import LogcatPage


class MockDeviceService(QObject):
    devices_changed = Signal(list)

    def __init__(self, devices: list[Device]) -> None:
        super().__init__()
        self._devices = devices

    def devices(self) -> list[Device]:
        return list(self._devices)

    def refresh(self) -> None:
        self.devices_changed.emit(self._devices)

    def start_polling(self, page_visible: bool = True) -> None:
        pass

    def stop_polling(self) -> None:
        pass

    def set_page_visible(self, visible: bool) -> None:
        pass


def _make_test_context(tmp_path: Path, devices: list[Device] | None = None) -> AppContext:
    if devices is None:
        devices = [
            Device(serial="EMU_5554", state="device", model="Pixel 7 Pro"),
            Device(serial="DEVICE_999", state="device", model="Galaxy S23"),
        ]
    settings = MagicMock()
    settings.data_dir = tmp_path / "data"
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    tool_locator = MagicMock()
    repository = MagicMock()
    device_service = MockDeviceService(devices)
    apk_service = MagicMock()

    return AppContext(
        settings=settings,
        tool_locator=tool_locator,
        repository=repository,
        device_service=device_service,  # type: ignore[arg-type]
        apk_service=apk_service,
    )


def _seed_test_lines(page: LogcatPage) -> None:
    test_lines = [
        "08-21 09:14:25.000 4821 4876 D SyncEngine: wakelock released",
        "08-21 09:14:26.000 4821 4877 D Analytics: dispatching update",
        "08-21 09:14:27.000 4821 4878 I Choreographer: cache hit for key config.v2",
        "08-21 09:14:28.000 4821 4879 W WindowManager: layout pass 14ms",
    ]
    for line in test_lines:
        page._model.queue(line)
    page._model._flush()


def test_logcat_page_initial_state(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)

    # Initial state should be clean and empty
    assert page._model.rowCount() == 0
    assert page._proxy.rowCount() == 0
    assert "0 lines" in page._count_label.text()
    assert page._device_combo.count() == 2
    assert page._device_combo.itemData(0) == "EMU_5554"
    assert not page._clear_button.isEnabled()
    assert not page._export_button.isEnabled()
    assert not page._pause_button.isEnabled()
    assert page._stream_button.isEnabled()


def test_logcat_page_level_filter(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)
    _seed_test_lines(page)

    # Queue an Error line so we have both D and E in the model
    page._model.queue("08-21 09:14:26.000 4821 4876 E TestTag: An error occurred")
    page._model._flush()

    total_count = page._model.rowCount()

    # Change filter to Error level
    page._level_combo.setCurrentText("E")
    page._apply_filters()

    filtered_count = page._proxy.rowCount()
    assert filtered_count >= 1
    assert filtered_count < total_count

    # Verify all visible items have level E or F
    for i in range(filtered_count):
        level = page._proxy.index(i, 3).data()
        assert level in ("E", "F")

    assert f"{filtered_count} / {total_count} lines" == page._count_label.text()


def test_logcat_page_tag_filter(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)
    _seed_test_lines(page)

    page._tag_input.setText("SyncEngine")
    page._apply_filters()

    filtered_count = page._proxy.rowCount()
    assert filtered_count > 0
    for i in range(filtered_count):
        tag = str(page._proxy.index(i, 4).data()).lower()
        assert "syncengine" in tag


def test_logcat_page_regex_filter(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)
    _seed_test_lines(page)

    page._regex_input.setText(r"wakelock|dispatching")
    page._apply_filters()

    filtered_count = page._proxy.rowCount()
    assert filtered_count > 0
    for i in range(filtered_count):
        msg = str(page._proxy.index(i, 5).data()).lower()
        assert "wakelock" in msg or "dispatching" in msg


def test_logcat_export_view_txt(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)
    _seed_test_lines(page)

    export_file = tmp_path / "exports" / "test_logcat.txt"
    visible_count = page._proxy.rowCount()

    exported_lines = page.export_view(export_file)
    assert exported_lines == visible_count
    assert export_file.exists()

    content = export_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == visible_count
    # Check that first line matches threadtime format
    first_line = content[0]
    assert len(first_line) > 20


def test_logcat_export_view_csv(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)
    _seed_test_lines(page)

    export_file = tmp_path / "exports" / "test_logcat.csv"
    visible_count = page._proxy.rowCount()

    exported_lines = page.export_view(export_file)
    assert exported_lines == visible_count
    assert export_file.exists()

    with export_file.open("r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    # First row is header
    assert reader[0] == ["Time", "PID", "TID", "Level", "Tag", "Message"]
    # Remaining rows match visible count
    assert len(reader) - 1 == visible_count


def test_logcat_export_filtered_subset(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)

    page._model.queue("08-21 09:14:26.000 4821 4876 E TestTag: Severe problem encountered")
    page._model._flush()

    page._level_combo.setCurrentText("E")
    page._apply_filters()
    filtered_count = page._proxy.rowCount()
    assert filtered_count >= 1

    export_file = tmp_path / "exports" / "errors_only.csv"
    exported_lines = page.export_view(export_file)

    assert exported_lines == filtered_count
    with export_file.open("r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    assert len(reader) - 1 == filtered_count
    for row in reader[1:]:
        assert row[3] in ("E", "F")


def test_logcat_on_export_clicked_dialog(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)
    _seed_test_lines(page)

    dest = tmp_path / "dialog_export.txt"

    with (
        patch(
            "PySide6.QtWidgets.QFileDialog.getSaveFileName",
            return_value=(str(dest), "Text Files (*.txt)"),
        ),
        patch("PySide6.QtWidgets.QMessageBox.information") as mock_info,
    ):
        page._export_button.click()
        assert dest.exists()
        assert mock_info.called
        assert "Successfully exported" in mock_info.call_args[0][2]


def test_logcat_on_export_clicked_empty_view(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)

    page._model.clear()

    with (
        patch("PySide6.QtWidgets.QFileDialog.getSaveFileName") as mock_dialog,
        patch("PySide6.QtWidgets.QMessageBox.information") as mock_info,
    ):
        page._on_export_clicked()
        assert not mock_dialog.called
        assert mock_info.called
        assert "no log lines to export" in mock_info.call_args[0][2].lower()


def test_logcat_select_device(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)

    page.select_device("DEVICE_999")
    assert page._device_combo.currentData() == "DEVICE_999"


def test_devices_page_open_logcat_button(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    devices_page = DevicesPage(ctx)

    # Select the first device row to populate detail card
    devices_page._table.selectRow(0)

    # Find the "≡  Open logcat" button inside detail card
    emitted_serials: list[str] = []
    devices_page.open_logcat_requested.connect(emitted_serials.append)

    open_logcat_btn = None
    for btn in devices_page._detail.findChildren(QPushButton):
        if "Open logcat" in btn.text():
            open_logcat_btn = btn
            break

    assert open_logcat_btn is not None
    open_logcat_btn.click()

    assert len(emitted_serials) == 1
    assert emitted_serials[0] == "EMU_5554"


def test_devices_page_refresh_no_devices_shows_alert(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path, devices=[])
    devices_page = DevicesPage(ctx)

    with patch("PySide6.QtWidgets.QMessageBox.information") as mock_info:
        devices_page._refresh_btn.click()
        assert mock_info.called
        assert "No Emulator Connected" in mock_info.call_args[0][1]


def test_logcat_button_states_and_pause_behavior(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)

    # 1. Initial button states: Not streaming -> pause disabled
    # Table starts clean & empty -> clear & export disabled
    assert page._model.rowCount() == 0
    assert page._pause_button.text() == "Pause"
    assert not page._pause_button.isEnabled()
    assert page._clear_button.text() == "Clear"
    assert not page._clear_button.isEnabled()
    assert page._export_button.text() == "Export view"
    assert not page._export_button.isEnabled()
    assert page._stream_button.text() == "Start stream"
    assert page._stream_button.isEnabled()
    assert page._device_combo.isEnabled()

    # 2. Adding new row enables Clear and Export
    page._model.queue("08-21 09:14:26.000 4821 4876 I TestTag: Hello logcat")
    page._model._flush()
    assert page._clear_button.isEnabled()
    assert page._export_button.isEnabled()

    # 3. Clearing rows disables Clear and Export buttons again
    page._clear_button.click()
    assert page._model.rowCount() == 0
    assert not page._clear_button.isEnabled()
    assert not page._export_button.isEnabled()

    # 4. Re-add row for filter and stream testing
    page._model.queue("08-21 09:14:26.000 4821 4876 I TestTag: Hello logcat")
    page._model._flush()
    assert page._clear_button.isEnabled()
    assert page._export_button.isEnabled()

    # 4. Filter matching 0 rows disables Export but keeps Clear enabled
    page._tag_input.setText("NonExistentTagXYZ")
    page._apply_filters()
    assert page._proxy.rowCount() == 0
    assert not page._export_button.isEnabled()
    assert page._clear_button.isEnabled()
    page._tag_input.clear()
    page._apply_filters()
    assert page._export_button.isEnabled()

    # 5. Streaming lifecycle and Pause button behavior
    mock_stream = MagicMock()
    mock_stream.line_received = MagicMock()
    mock_stream.finished = MagicMock()
    mock_adb = MagicMock()
    mock_adb.logcat_stream.return_value = mock_stream
    page._ctx.device_service._adb = mock_adb

    # Start stream
    page._stream_button.click()
    assert page._stream_button.text() == "Stop stream"
    assert page._pause_button.isEnabled()
    assert not page._device_combo.isEnabled()

    # Pause (text-only, no icon)
    page._pause_button.click()
    assert page._pause_button.text() == "Resume"
    assert page._model._paused is True

    # Resume (text-only, no icon)
    page._pause_button.click()
    assert page._pause_button.text() == "Pause"
    assert page._model._paused is False

    # Pause again, then stop stream -> Pause button resets and becomes disabled
    page._pause_button.click()
    assert page._pause_button.text() == "Resume"
    assert page._model._paused is True

    page._stream_button.click()
    assert page._stream_button.text() == "Start stream"
    assert not page._pause_button.isEnabled()
    assert page._pause_button.text() == "Pause"
    assert not page._pause_button.isChecked()
    assert page._model._paused is False
    assert page._device_combo.isEnabled()

    # Finish stream via signal
    page._stream_button.click()
    assert page._pause_button.isEnabled()
    page._on_stream_finished()
    assert page._stream_button.text() == "Start stream"
    assert not page._pause_button.isEnabled()
    assert page._pause_button.text() == "Pause"


def test_logcat_no_devices_shows_alert_on_stream_click(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path, devices=[])
    page = LogcatPage(ctx)

    assert page._stream_button.isEnabled()
    assert not page._device_combo.isEnabled()
    assert not page._pause_button.isEnabled()
    assert page._device_combo.currentText() == "No emulator connected"

    with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warning:
        page._stream_button.click()
        assert mock_warning.called
        assert "No Emulator Connected" in mock_warning.call_args[0][1]
        assert not page._stream_button.isChecked()
