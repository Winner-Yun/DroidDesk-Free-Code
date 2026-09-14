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


def test_logcat_page_initial_state(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)

    assert page._model.rowCount() > 0
    assert page._proxy.rowCount() == page._model.rowCount()
    assert f"{page._model.rowCount()} lines" in page._count_label.text()
    assert page._device_combo.count() == 2
    assert page._device_combo.itemData(0) == "EMU_5554"


def test_logcat_page_level_filter(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_test_context(tmp_path)
    page = LogcatPage(ctx)

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
