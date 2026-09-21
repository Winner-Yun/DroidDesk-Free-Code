from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from droiddesk.context import AppContext
from droiddesk.core.models import ApkInfo, Device
from droiddesk.ui.pages.analyzer import AnalyzerPage
from droiddesk.ui.pages.apk_tester import ApkTesterPage
from droiddesk.ui.pages.commands import CommandsPage
from droiddesk.ui.pages.dashboard import DashboardPage
from droiddesk.ui.pages.gate import GatePage
from droiddesk.ui.pages.organizer import OrganizerPage
from droiddesk.ui.pages.reports import ReportsPage
from droiddesk.ui.pages.security import SecurityPage
from droiddesk.ui.widgets.empty_state import EmptyStateWidget


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
    device_service.devices_changed = MagicMock()

    apk_service = MagicMock()
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


def test_empty_state_widget_signals(qapp: QApplication) -> None:
    # Standard full-page mode
    widget = EmptyStateWidget(
        title="No APK",
        message="Please upload",
        button_text="Upload APK",
    )
    mock_slot = MagicMock()
    widget.upload_requested.connect(mock_slot)
    widget._upload_btn.click()
    mock_slot.assert_called_once()
    assert widget._title_label.text() == "No APK"
    assert widget._message_label.text() == "Please upload"

    # Compact banner mode
    compact_widget = EmptyStateWidget(
        title="Compact Title",
        message="Compact Message",
        compact=True,
    )
    assert compact_widget._title_label.text() == "Compact Title"
    compact_widget.set_title("New Compact Title")
    assert compact_widget._title_label.text() == "New Compact Title"
    compact_widget.set_message("New Compact Msg")
    assert compact_widget._message_label.text() == "New Compact Msg"
    compact_widget.set_button_visible(False)
    assert compact_widget._upload_btn.isHidden()

    # Frameless inline mode (for nested cards)
    frameless_widget = EmptyStateWidget(
        title="Frameless Title",
        message="Frameless Message",
        frameless=True,
    )
    assert frameless_widget._title_label.text() == "Frameless Title"
    frameless_slot = MagicMock()
    frameless_widget.upload_requested.connect(frameless_slot)
    frameless_widget._upload_btn.click()
    frameless_slot.assert_called_once()


def test_analyzer_page_empty_state(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = AnalyzerPage(ctx)

    # Initially without APK: empty state not hidden, tabs hidden
    assert not page._empty_state.isHidden()
    assert page._tabs.isHidden()

    upload_slot = MagicMock()
    page.upload_requested.connect(upload_slot)
    page._empty_state._upload_btn.click()
    upload_slot.assert_called_once()

    # Load an APK: empty state hidden, tabs shown
    apk_info = ApkInfo(
        file_path=tmp_path / "app.apk",
        file_hash="h1",
        package_name="com.test.app",
        version_name="1.0",
        version_code=1,
    )
    ctx.apk_service.inspect = MagicMock(return_value=apk_info)  # type: ignore[method-assign]
    ctx.apk_service.inspect_full = MagicMock(return_value=apk_info)  # type: ignore[method-assign]

    page.load_apk(apk_info.file_path)
    assert page._empty_state.isHidden()
    assert not page._tabs.isHidden()

    # Reset to None: empty state visible again
    page.load_apk(None)
    assert page._tabs.isHidden()
    assert not page._empty_state.isHidden()


def test_apk_tester_page_empty_state(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = ApkTesterPage(ctx)

    assert not page._artifact_empty_state.isHidden()
    assert page._artifact_details.isHidden()

    upload_slot = MagicMock()
    page.upload_requested.connect(upload_slot)
    page._artifact_empty_state._upload_btn.click()
    upload_slot.assert_called_once()

    # Select an APK
    apk_file = tmp_path / "app.apk"
    apk_file.write_bytes(b"dummy")
    apk_info = ApkInfo(
        file_path=apk_file,
        file_hash="h1",
        package_name="com.test.app",
        version_name="1.0",
        version_code=1,
    )
    ctx.apk_service.inspect = MagicMock(return_value=apk_info)  # type: ignore[method-assign]
    page._on_apk_selected(apk_file)

    assert page._artifact_empty_state.isHidden()
    assert not page._artifact_details.isHidden()


def test_gate_page_empty_state(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = GatePage(ctx)

    # Initial state: no APK, content hidden, empty state visible
    assert not page._empty_state.isHidden()
    assert page._content_container.isHidden()

    upload_slot = MagicMock()
    page.upload_requested.connect(upload_slot)
    page._empty_state._upload_btn.click()
    upload_slot.assert_called_once()

    # Set APK
    page.set_apk(tmp_path / "app.apk")
    assert page._empty_state.isHidden()
    assert not page._content_container.isHidden()

    # Remove APK
    page.set_apk(None)
    assert not page._empty_state.isHidden()
    assert page._content_container.isHidden()


def test_dashboard_reports_security_commands_empty_states(
    qapp: QApplication, tmp_path: Path
) -> None:
    ctx = _make_mock_context(tmp_path)

    dashboard = DashboardPage(ctx)
    assert not dashboard._empty_banner.isHidden()
    dashboard.set_apk(tmp_path / "app.apk")
    assert dashboard._empty_banner.isHidden()

    reports = ReportsPage(ctx)
    assert not reports._empty_state.isHidden()
    reports.set_apk(tmp_path / "app.apk")
    assert reports._empty_state.isHidden()

    security = SecurityPage(ctx)
    assert not security._empty_banner.isHidden()
    security.set_apk(tmp_path / "app.apk")
    assert security._empty_banner.isHidden()

    commands = CommandsPage(ctx)
    assert not commands._empty_banner.isHidden()
    commands.set_apk(tmp_path / "app.apk")
    assert commands._empty_banner.isHidden()

    organizer = OrganizerPage(ctx)
    assert not organizer._empty_banner.isHidden()
    organizer.set_apk(tmp_path / "app.apk")
    assert organizer._empty_banner.isHidden()
