"""ScanService - Section 6.5 and 6.6. Two-stage secret scanning: gitleaks (stage
one, subprocess, JSON report) merged with DroidDesk's own engine (stage two, Android
rules + entropy). Also drives the APK Privacy Scanner (archive enumeration, resource
string extraction, opt-in DEX deep scan). CPU-bound work runs off the UI thread via
QThreadPool; every long scan must be cancellable (Section 4.2).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from droiddesk.core.errors import ToolNotFoundError
from droiddesk.core.models import Finding, ScanResult
from droiddesk.infra.apk_reader import ApkReader
from droiddesk.infra.process import ProcessRunner
from droiddesk.infra.scanner.engine import ScannerEngine
from droiddesk.infra.scanner.gitleaks_mapping import get_gitleaks_severity
from droiddesk.infra.scanner.util import hash_match, redact_secret
from droiddesk.infra.suppressions import SuppressionManager
from droiddesk.infra.tools import ToolLocator


class _ScanWorker(QRunnable):
    def __init__(self, service: ScanService, target: Path, is_apk: bool = False) -> None:
        super().__init__()
        self._service = service
        self._target = target
        self._is_apk = is_apk

    def run(self) -> None:
        try:
            if self._is_apk:
                result = self._service.scan_apk(self._target)
            else:
                result = self._service.scan_project(self._target)
            if self._service.is_cancelled():
                self._service.cancelled.emit()
            else:
                self._service.finished.emit(result)
        except Exception as exc:
            if self._service.is_cancelled():
                self._service.cancelled.emit()
            else:
                self._service.failed.emit(str(exc))


class ScanService(QObject):
    progress = Signal(int, int)
    finished = Signal(object)  # ScanResult
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        tool_locator: ToolLocator,
        engine: ScannerEngine | None = None,
        apk_reader: ApkReader | None = None,
    ) -> None:
        super().__init__()
        self._tools = tool_locator
        self._engine = engine or ScannerEngine()
        self._apk_reader = apk_reader or ApkReader(tool_locator=tool_locator)
        self._runner = ProcessRunner()
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def is_cancelled(self) -> bool:
        return self._cancel_requested

    def scan_project(self, project_root: Path) -> ScanResult:
        started_at = datetime.now(UTC)
        t0 = time.perf_counter()
        self._cancel_requested = False

        # 1. Run Gitleaks (if available)
        gitleaks_findings: list[Finding] = []
        if not self._cancel_requested:
            gitleaks_findings = self._run_gitleaks(project_root)

        # 2. Run ScannerEngine tree walk with cancellation check
        engine_findings = self._engine.scan_tree(
            project_root, is_cancelled=lambda: self._cancel_requested
        )

        # 3. Merge & deduplicate
        merged = _merge_and_dedup(gitleaks_findings, engine_findings)

        # 4. Apply suppressions from .droiddesk/suppressions.toml
        supp_manager = SuppressionManager(project_root)
        supp_manager.apply_suppressions(merged)

        # Count total scanned files efficiently
        files_scanned = 0
        for _dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [
                d
                for d in dirnames
                if d not in self._engine._excluded_dirs and not d.startswith(".")
            ]
            files_scanned += len(filenames)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ScanResult(
            target_type="project",
            target_path=project_root,
            started_at=started_at,
            findings=merged,
            files_scanned=files_scanned,
            duration_ms=duration_ms,
        )

    def scan_project_async(self, project_root: Path) -> None:
        """Run project scanning asynchronously on QThreadPool."""
        self._cancel_requested = False
        worker = _ScanWorker(self, project_root, is_apk=False)
        QThreadPool.globalInstance().start(worker)

    def scan_apk_async(self, apk_path: Path) -> None:
        """Run APK scanning asynchronously on QThreadPool."""
        self._cancel_requested = False
        worker = _ScanWorker(self, apk_path, is_apk=True)
        QThreadPool.globalInstance().start(worker)

    def scan_apk(self, apk_path: Path) -> ScanResult:
        started_at = datetime.now(UTC)
        t0 = time.perf_counter()
        self._cancel_requested = False

        findings: list[Finding] = []
        files_scanned = 0

        # Persistent extraction directory so files can be opened in File Explorer
        extract_dir = apk_path.parent / f"{apk_path.stem}_extracted"
        try:
            extract_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            extract_dir = Path(tempfile.gettempdir()) / "droiddesk_extracted" / apk_path.stem
            extract_dir.mkdir(parents=True, exist_ok=True)

        # 1. Extract assets/ and res/raw/ to the extraction directory
        with zipfile.ZipFile(apk_path, "r") as z:
            for name in z.namelist():
                if self._cancel_requested:
                    break
                if name.startswith(("assets/", "res/raw/")) and not name.endswith("/"):
                    z.extract(name, extract_dir)
                    files_scanned += 1

        # 2. Extract string resources from resources.arsc into res/values/strings.xml
        # (This is the original file that contains string tokens in Android projects)
        if not self._cancel_requested:
            try:
                named_strings = self._apk_reader.extract_named_string_resources(apk_path)
                if named_strings:
                    values_dir = extract_dir / "res" / "values"
                    values_dir.mkdir(parents=True, exist_ok=True)
                    strings_xml = values_dir / "strings.xml"

                    xml_lines = [
                        '<?xml version="1.0" encoding="utf-8"?>',
                        "<resources>",
                    ]
                    seen_names: set[str] = set()
                    for idx, (res_name, val) in enumerate(named_strings, start=1):
                        name_key = res_name.strip() if res_name else f"string_{idx}"
                        if name_key in seen_names:
                            name_key = f"{name_key}_{idx}"
                        seen_names.add(name_key)
                        safe_val = (
                            val.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                            .replace('"', "&quot;")
                        )
                        xml_lines.append(f'    <string name="{name_key}">{safe_val}</string>')
                    xml_lines.append("</resources>\n")

                    strings_xml.write_text("\n".join(xml_lines), encoding="utf-8")
                    files_scanned += 1
            except Exception:
                pass

        # 3. Scan the extracted tree (assets, res/raw, and res/values/strings.xml)
        if not self._cancel_requested:
            findings = self._engine.scan_tree(
                extract_dir, is_cancelled=lambda: self._cancel_requested
            )

        merged = _merge_and_dedup(findings)

        # Apply suppressions from project parent if available
        supp_manager = SuppressionManager(apk_path.parent)
        supp_manager.apply_suppressions(merged)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ScanResult(
            target_type="apk",
            target_path=apk_path,
            started_at=started_at,
            findings=merged,
            files_scanned=files_scanned,
            duration_ms=duration_ms,
        )

    def _run_gitleaks(self, target: Path) -> list[Finding]:
        try:
            gitleaks_path = self._tools.resolve("gitleaks")
        except ToolNotFoundError:
            # Gitleaks not found; continue without it
            return []

        try:
            result = self._runner.run(
                gitleaks_path,
                [
                    "detect",
                    f"--source={target}",
                    "--report-format=json",
                    "--report-path=-",
                    "--no-banner",
                ],
                timeout=120.0,
            )
        except Exception:
            # Subprocess execution error; continue without Gitleaks
            return []

        findings: list[Finding] = []
        try:
            data = json.loads(result.stdout or "[]")
            if not isinstance(data, list):
                return []
            for item in data:
                if not isinstance(item, dict):
                    continue
                rule_id = str(item.get("RuleID", "gitleaks-finding"))
                desc = str(item.get("Description", ""))
                secret_val = str(item.get("Secret") or item.get("Match") or "")
                file_str = str(item.get("File", ""))
                file_path = Path(file_str)
                if not file_path.is_absolute():
                    file_path = target / file_path

                line_val = item.get("StartLine")
                line_number = int(line_val) if line_val is not None else None

                findings.append(
                    Finding(
                        rule_id=rule_id,
                        severity=get_gitleaks_severity(rule_id, desc),
                        file_path=file_path,
                        line_number=line_number,
                        match_hash=hash_match(secret_val),
                        redacted=redact_secret(secret_val),
                    )
                )
        except Exception:
            return []

        return findings


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
