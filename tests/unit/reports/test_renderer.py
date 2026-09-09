import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from droiddesk.core.models import ApkInfo, TestRun, TestStepResult
from droiddesk.core.severity import Verdict
from droiddesk.reports.renderer import html_to_pdf
from droiddesk.services.report_service import ReportService


def test_html_to_pdf_missing_gtk_raises_runtime_error() -> None:
    # On Windows without GTK3 runtime installed, importing weasyprint raises OSError
    with pytest.raises(RuntimeError, match="WeasyPrint failed to load"):
        html_to_pdf("<html><body>Hello</body></html>")


def test_html_to_pdf_with_mocked_weasyprint(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_html_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.write_pdf.return_value = b"%PDF-1.4 dummy binary pdf stream"
    mock_html_cls.return_value = mock_instance

    mock_module = MagicMock()
    mock_module.HTML = mock_html_cls

    monkeypatch.setitem(sys.modules, "weasyprint", mock_module)

    pdf = html_to_pdf("<html><body>Hello</body></html>")
    assert pdf == b"%PDF-1.4 dummy binary pdf stream"
    mock_html_cls.assert_called_once_with(string="<html><body>Hello</body></html>")
    mock_instance.write_pdf.assert_called_once()


def test_render_test_report_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    apk = ApkInfo(
        file_path=Path("sample.apk"),
        file_hash="hash_123",
        package_name="com.test.reporter",
        version_name="2.1.0",
        version_code=42,
    )
    run = TestRun(
        apk=apk,
        device_serial="DEVICE_XYZ",
        profile_name="Smoke",
        started_at=datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC),
        steps=[
            TestStepResult("Validate", True, 50, "ok"),
            TestStepResult("Install", True, 200, "Success"),
        ],
        verdict=Verdict.PASS,
        duration_ms=250,
        log_excerpt="Log excerpt line 1\nLog excerpt line 2",
    )

    service = ReportService()

    # 1. HTML
    html_output = service.render_test_report(run, "html")
    assert isinstance(html_output, str)
    assert "<!doctype html>" in html_output
    assert "com.test.reporter" in html_output
    assert "DEVICE_XYZ" in html_output
    assert "PASS" in html_output

    # 2. JSON
    json_output = service.render_test_report(run, "json")
    assert isinstance(json_output, str)
    data = json.loads(json_output)
    assert data["apk"]["package_name"] == "com.test.reporter"
    assert data["device_serial"] == "DEVICE_XYZ"
    assert data["verdict"] == "PASS"

    # 3. Markdown
    md_output = service.render_test_report(run, "markdown")
    assert isinstance(md_output, str)
    assert "# Test Report — com.test.reporter" in md_output
    assert "| Validate | PASS | 50 | ok |" in md_output

    # 4. PDF (mock html_to_pdf to verify delegation)
    monkeypatch.setattr(
        "droiddesk.reports.renderer.html_to_pdf",
        lambda _html: b"%PDF-mock",
    )
    pdf_output = service.render_test_report(run, "pdf")
    assert pdf_output == b"%PDF-mock"
