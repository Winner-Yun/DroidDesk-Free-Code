from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from droiddesk.context import AppContext
from droiddesk.core.models import ApkInfo
from droiddesk.ui.pages.analyzer import AnalyzerPage


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


def test_analyzer_page_signature_panel_debug_keystore(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = AnalyzerPage(ctx)

    apk_info = ApkInfo(
        file_path=tmp_path / "test.apk",
        file_hash="hash123",
        package_name="com.test.app",
        version_name="1.0.0",
        version_code=1,
        signature_schemes=[2],
        signature_verified=True,
        signature_source="apksigner",
        certificate_dn="C=US, O=Android, CN=Android Debug",
        certificate_fingerprint_sha256="9F:8D:1A:12:94:CB:7A:34",
        certificate_fingerprint_sha1="13:C6:13:57:8D:73",
        certificate_fingerprint_md5="66:50:43:DF:FD:5C",
    )
    ctx.apk_service.inspect = MagicMock(return_value=apk_info)  # type: ignore[method-assign]
    ctx.apk_service.inspect_full = MagicMock(return_value=apk_info)  # type: ignore[method-assign]

    page.load_apk(apk_info.file_path)

    # Verify signature panel is built
    assert page._sig_panel is not None
    labels = [lbl.text() for lbl in page._sig_panel.findChildren(QLabel)]

    # Verified badge
    assert any("Verified" in t for t in labels)
    # Debug keystore banner
    assert any("Android Debug Keystore Signature" in t for t in labels)
    # Subject DN
    assert any("CN=Android Debug" in t for t in labels)
    # Fingerprints
    assert any("9F:8D:1A:12:94:CB:7A:34" in t for t in labels)
    assert any("13:C6:13:57:8D:73" in t for t in labels)
    assert any("66:50:43:DF:FD:5C" in t for t in labels)
    # Source note
    assert any("apksigner verify" in t for t in labels)


def test_analyzer_page_signature_panel_release_keystore(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = AnalyzerPage(ctx)

    apk_info = ApkInfo(
        file_path=tmp_path / "release.apk",
        file_hash="rel_hash",
        package_name="com.mycompany.app",
        version_name="2.1.0",
        version_code=21,
        signature_schemes=[1, 2, 3],
        signature_verified=True,
        signature_source="apksigner",
        certificate_dn="CN=Acme Production, O=Acme Corp, C=US",
        certificate_fingerprint_sha256="AA:BB:CC:DD",
    )
    ctx.apk_service.inspect = MagicMock(return_value=apk_info)  # type: ignore[method-assign]
    ctx.apk_service.inspect_full = MagicMock(return_value=apk_info)  # type: ignore[method-assign]

    page.load_apk(apk_info.file_path)

    labels = [lbl.text() for lbl in page._sig_panel.findChildren(QLabel)]
    assert any("CN=Acme Production" in t for t in labels)
    # No debug keystore banner for release APK
    assert not any("Android Debug Keystore Signature" in t for t in labels)


def test_analyzer_page_no_compare_button(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = AnalyzerPage(ctx)
    buttons = [btn.text() for btn in page.findChildren(QPushButton)]
    assert not any("Compare" in text for text in buttons)

