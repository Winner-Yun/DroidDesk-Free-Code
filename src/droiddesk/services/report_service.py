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
        # TODO(Phase 3): render reports/templates/test_report.html with `run`;
        # convert to PDF via WeasyPrint when fmt == "pdf".
        raise NotImplementedError

    def render_gate_report(self, result: GateResult, fmt: ReportFormat) -> str | bytes:
        # TODO(Phase 5): render reports/templates/gate.html with `result`.
        raise NotImplementedError

    def render_scan_report(self, result: ScanResult, fmt: ReportFormat) -> str | bytes:
        # TODO(Phase 4): findings grouped by severity, redacted previews only.
        raise NotImplementedError
