"""ReportService — Section 6.13. One Jinja2 template set renders every format:
HTML is the source of truth, PDF is produced from it via WeasyPrint (ReportLab is
the documented fallback if WeasyPrint's GTK dependency proves awkward to bundle —
see Section 2.2 and 10.1), JSON is serialized directly from the domain model, and
Markdown is derived for pasting into a PR description.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from jinja2 import Environment as JinjaEnvironment
from jinja2 import FileSystemLoader

from droiddesk.core.models import GateResult, ScanResult, TestRun

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
                from droiddesk.reports.renderer import html_to_pdf

                return html_to_pdf(html)
            case "json":
                import dataclasses
                import json

                return json.dumps(dataclasses.asdict(run), default=str, indent=2)
            case "markdown":
                lines = [
                    f"# Test Report — {run.apk.package_name}",
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

    def render_gate_report(self, result: GateResult, fmt: ReportFormat) -> str | bytes:
        # TODO(Phase 5): render reports/templates/gate.html with `result`.
        raise NotImplementedError

    def render_scan_report(self, result: ScanResult, fmt: ReportFormat) -> str | bytes:
        # TODO(Phase 4): findings grouped by severity, redacted previews only.
        raise NotImplementedError
