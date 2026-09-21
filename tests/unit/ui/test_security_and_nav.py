from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from droiddesk.context import AppContext
from droiddesk.core.models import Finding
from droiddesk.core.severity import Severity
from droiddesk.ui.pages.security import SecurityPage
from droiddesk.ui.widgets.nav_sidebar import NavEntry, NavSidebar, _NavButton


def _make_mock_context(tmp_path: Path) -> AppContext:
    settings = MagicMock()
    settings.data_dir = tmp_path / "data"
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    tool_locator = MagicMock()
    repository = MagicMock()
    device_service = MagicMock()
    apk_service = MagicMock()

    return AppContext(
        settings=settings,
        tool_locator=tool_locator,
        repository=repository,
        device_service=device_service,
        apk_service=apk_service,
    )


def test_nav_sidebar_badge(qapp: QApplication) -> None:
    entry = NavEntry("test_key", "⛨", "Test Label")
    btn = _NavButton(entry)
    assert btn._badge.isHidden()

    # Setting badge shows it
    btn.set_badge(3)
    assert not btn._badge.isHidden()
    assert btn._badge.text() == "3"

    # Clearing badge hides it
    btn.set_badge(0)
    assert btn._badge.isHidden()
    btn.set_badge(None)
    assert btn._badge.isHidden()

    # Test NavSidebar set_badge
    sidebar = NavSidebar()
    sidebar.set_badge("security", 5)
    sec_btn = sidebar._buttons["security"]
    assert not sec_btn._badge.isHidden()
    assert sec_btn._badge.text() == "5"

    sidebar.set_badge("security", None)
    assert sec_btn._badge.isHidden()


def test_security_page_splitter_and_details(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = SecurityPage(ctx)

    assert page._splitter is not None
    assert page._splitter.count() == 2
    assert page._table is not None

    # Test set_apk button text and banner
    assert page._scan_button.text() == "Scan project"
    sample_apk = tmp_path / "app.apk"
    sample_apk.write_bytes(b"dummy")
    page.set_apk(sample_apk)
    assert page._scan_button.text() == "Scan APK (app.apk)"
    assert page._empty_banner.isHidden()

    page.set_apk(None)
    assert page._scan_button.text() == "Scan project"
    assert not page._empty_banner.isHidden()

    # Create dummy XML file for findings
    xml_file = tmp_path / "strings.xml"
    xml_file.write_text(
        '<?xml version="1.0"?>\n<resources>\n  <string name="k">token123</string>\n</resources>',
        encoding="utf-8",
    )

    finding = Finding(
        rule_id="test-rule",
        severity=Severity.HIGH,
        file_path=xml_file,
        match_hash="hash1",
        redacted="token123",
        line_number=3,
    )

    badge_slot = MagicMock()
    page.findings_changed.connect(badge_slot)

    from datetime import UTC, datetime

    from droiddesk.core.models import ScanResult

    result = ScanResult(
        target_type="project",
        target_path=tmp_path,
        started_at=datetime.now(UTC),
        findings=[finding],
        files_scanned=1,
        duration_ms=10,
    )
    page._on_scan_finished(result)

    badge_slot.assert_called_once_with(1)
    assert page._proxy.rowCount() == 1
    assert page._active_finding == finding
    assert page._detail is not None


def test_code_view_line_and_token_highlighting(qapp: QApplication) -> None:
    from droiddesk.ui.widgets.code_view import CodeView

    cv = CodeView()
    sample_text = 'line 1\nline 2\n<string name="key">MY_SECRET_TOKEN_123</string>\nline 4\n'
    cv.set_text(sample_text, highlight_line=3, token="MY_SECRET_TOKEN_123")

    assert cv._highlighted_line == 3
    assert cv.line_number_area_width() > 0
    selections = cv.extraSelections()
    assert len(selections) >= 2
    assert any(s.cursor.selectedText() == "MY_SECRET_TOKEN_123" for s in selections)

    # Clearing highlight
    cv.highlight_line(None)
    assert cv._highlighted_line is None
    assert len(cv.extraSelections()) == 0


def test_rule_id_to_key_name_and_findings_model(tmp_path: Path) -> None:
    from PySide6.QtCore import Qt

    from droiddesk.infra.scanner.gitleaks_mapping import rule_id_to_key_name
    from droiddesk.ui.models.findings_model import FindingsModel

    assert rule_id_to_key_name("android-firebase-legacy-token") == "FIREBASE_API_KEY"
    assert rule_id_to_key_name("android-maps-api-key") == "GOOGLE_MAPS_API_KEY"
    assert rule_id_to_key_name("aws-access-key-id") == "AWS_ACCESS_KEY_ID"
    assert rule_id_to_key_name("my-custom-token") == "MY_CUSTOM_TOKEN"

    model = FindingsModel()
    assert model.headerData(1, Qt.Orientation.Horizontal) == "Key Name"

    f = Finding(
        rule_id="android-firebase-legacy-token",
        severity=Severity.HIGH,
        file_path=tmp_path / "strings.xml",
        match_hash="h1",
        redacted="secret123",
        line_number=10,
    )
    model.set_findings([f])
    index = model.index(0, 1)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "FIREBASE_API_KEY"
    expected_tip = "Rule ID: android-firebase-legacy-token"
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) == expected_tip


def test_engine_key_disambiguation(tmp_path: Path) -> None:
    from droiddesk.infra.scanner.engine import ScannerEngine
    from droiddesk.infra.scanner.gitleaks_mapping import rule_id_to_key_name

    engine = ScannerEngine()

    cases = [
        (
            '<string name="firebase_key">AIzaSyFakeFirebaseApiKey1234567890abcdef</string>',
            "FIREBASE_API_KEY",
            "firebase-api-key",
        ),
        (
            '<string name="google_api_key">AIzaSy012345678901234567890123456789012</string>',
            "FIREBASE_API_KEY",
            "firebase-api-key",
        ),
        (
            '<string name="firebase_api_key">AIzaSy012345678901234567890123456789012</string>',
            "FIREBASE_API_KEY",
            "firebase-api-key",
        ),
        (
            '<string name="google_map_apk_key">AIzaSy012345678901234567890123456789012</string>',
            "GOOGLE_MAPS_API_KEY",
            "android-maps-api-key",
        ),
        (
            '<string name="google_maps_key">AIzaSy012345678901234567890123456789012</string>',
            "GOOGLE_MAPS_API_KEY",
            "android-maps-api-key",
        ),
        (
            '<string name="maps_api_key">AIzaSy012345678901234567890123456789012</string>',
            "GOOGLE_MAPS_API_KEY",
            "android-maps-api-key",
        ),
        (
            '<meta-data android:name="com.google.android.geo.API_KEY" '
            'android:value="AIzaSy012345678901234567890123456789012" />',
            "GOOGLE_MAPS_API_KEY",
            "android-maps-api-key",
        ),
        (
            '<string name="legacy_token">AIzaSy012345678901234567890123456789012</string>',
            "FIREBASE_API_KEY",
            "android-firebase-legacy-token",
        ),
        (
            '<string name="general_api_key">AIzaSy012345678901234567890123456789012</string>',
            "GOOGLE_API_KEY",
            "google-api-key",
        ),
    ]

    for idx, (xml_content, expected_key, expected_rule) in enumerate(cases):
        test_file = tmp_path / f"test_{idx}.xml"
        test_file.write_text(xml_content, encoding="utf-8")
        findings = engine.scan_file(test_file)
        assert len(findings) >= 1, f"Failed finding for {xml_content}"
        first = findings[0]
        assert first.rule_id == expected_rule
        assert rule_id_to_key_name(first.rule_id) == expected_key

    # Test google-services.json context
    gs_file = tmp_path / "google-services.json"
    gs_payload = '{"api_key": [{"current_key": "AIzaSy012345678901234567890123456789012"}]}'
    gs_file.write_text(gs_payload, encoding="utf-8")
    gs_findings = engine.scan_file(gs_file)
    assert any(rule_id_to_key_name(f.rule_id) == "FIREBASE_API_KEY" for f in gs_findings)
