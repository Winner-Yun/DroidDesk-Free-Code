"""Report generation service.

Renders scan and test run reports into HTML, PDF, JSON, and Markdown formats.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Literal

from jinja2 import Environment as JinjaEnvironment
from jinja2 import FileSystemLoader

from droiddesk.core.models import ScanResult, TestRun
from droiddesk.reports.renderer import html_to_pdf

ReportFormat = Literal["html", "pdf", "json", "markdown"]

_TEMPLATES_DIR = Path(__file__).parent.parent / "reports" / "templates"


class ReportService:
    def __init__(self) -> None:
        self._jinja = JinjaEnvironment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)

    def render_test_report(self, run: TestRun, fmt: ReportFormat) -> str | bytes:
        template = self._jinja.get_template("test_report.html")
        html = template.render(run=run)

        match fmt:
            case "html":
                return html
            case "pdf":
                return html_to_pdf(html)
            case "json":
                return json.dumps(dataclasses.asdict(run), default=str, indent=2)
            case "markdown":
                lines = [
                    f"# Test Report - {run.apk.package_name}",
                    f"**Verdict:** {run.verdict} | **Device:** {run.device_serial} | "
                    f"**Profile:** {run.profile_name}",
                    "",
                    "## Steps",
                    "| Step | Result | Duration (ms) | Detail |",
                    "| --- | --- | --- | --- |",
                ]
                for step in run.steps:
                    status = "PASS" if step.passed else "FAIL"
                    lines.append(f"| {step.name} | {status} | {step.duration_ms} | {step.detail} |")
                return "\n".join(lines)
            case _:
                raise ValueError(f"Unknown report format: {fmt}")

    def render_scan_report(self, result: ScanResult, fmt: ReportFormat) -> str | bytes:
        template = self._jinja.get_template("scan_report.html")
        html = template.render(result=result)

        match fmt:
            case "html":
                return html
            case "pdf":
                return html_to_pdf(html)
            case "json":
                return json.dumps(dataclasses.asdict(result), default=str, indent=2)
            case "markdown":
                lines = [
                    f"# Secret Scan Report - {result.target_path.name}",
                    f"**Target:** {result.target_path} ({result.target_type}) | "
                    f"**Files:** {result.files_scanned} | **Duration:** {result.duration_ms} ms",
                    "",
                    f"## Findings ({len(result.findings)})",
                    "| Rule ID | Severity | File | Line | Redacted Secret | Status |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
                for finding in result.findings:
                    line_no = str(finding.line_number) if finding.line_number is not None else "-"
                    status = "Suppressed" if finding.suppressed else "Active"
                    lines.append(
                        f"| {finding.rule_id} | {finding.severity.name} | "
                        f"{finding.file_path.name} | {line_no} | `{finding.redacted}` | {status} |"
                    )
                return "\n".join(lines)
            case _:
                raise ValueError(f"Unknown report format: {fmt}")
