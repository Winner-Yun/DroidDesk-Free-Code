"""ScanService — Section 6.5 and 6.6. Two-stage secret scanning: gitleaks (stage
one, subprocess, JSON report) merged with DroidDesk's own engine (stage two, Android
rules + entropy). Also drives the APK Privacy Scanner (archive enumeration, resource
string extraction, opt-in DEX deep scan). CPU-bound work runs off the UI thread via
QThreadPool; every long scan must be cancellable (Section 4.2).
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from droiddesk.core.models import Finding, ScanResult
from droiddesk.infra.process import ProcessRunner
from droiddesk.infra.scanner.engine import ScannerEngine
from droiddesk.infra.tools import ToolLocator


class ScanService(QObject):
    progress = Signal(int, int)
    finished = Signal(object)  # ScanResult
    cancelled = Signal()

    def __init__(self, tool_locator: ToolLocator, engine: ScannerEngine | None = None) -> None:
        super().__init__()
        self._tools = tool_locator
        self._engine = engine or ScannerEngine()
        self._runner = ProcessRunner()
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def scan_project(self, project_root: Path) -> ScanResult:
        gitleaks_findings = self._run_gitleaks(project_root)
        engine_findings = self._engine.scan_tree(project_root)
        merged = _merge_and_dedup(gitleaks_findings, engine_findings)

        # TODO(Phase 4): populate started_at / files_scanned / duration_ms, apply
        # suppressions from .droiddesk/suppressions.toml, run on a QThreadPool
        # worker and emit progress instead of blocking.
        raise NotImplementedError

    def scan_apk(self, apk_path: Path) -> ScanResult:
        # TODO(Phase 4): enumerate the APK as a ZIP, extract assets/ and
        # res/raw/ to a temp dir, run self._engine over it, plus
        # ApkReader.extract_string_resources for resources.arsc strings.
        raise NotImplementedError

    def _run_gitleaks(self, target: Path) -> list[Finding]:
        gitleaks_path = self._tools.resolve("gitleaks")
        result = self._runner.run(
            gitleaks_path,
            ["detect", f"--source={target}", "--report-format=json", "--report-path=-", "--no-banner"],
            timeout=120.0,
        )
        # TODO(Phase 4): parse the JSON report into Finding objects.
        json.loads(result.stdout or "[]")
        return []


def _merge_and_dedup(*finding_lists: list[Finding]) -> list[Finding]:
    seen: set[tuple[Path, int | None, str]] = set()
    merged: list[Finding] = []
    for findings in finding_lists:
        for finding in findings:
            key = (finding.file_path, finding.line_number, finding.rule_id)
            if key in seen:
                continue
            seen.add(key)
            merged.append(finding)
    return merged
