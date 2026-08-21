"""Domain models: pure data, no I/O. Mirrors the SQLite schema in Section 7 plus the
in-memory shapes (Device, Finding) that are not persisted directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from droiddesk.core.severity import GateVerdict, Severity, Verdict


@dataclass(slots=True)
class Device:
    serial: str
    state: str  # device | unauthorized | offline
    model: str | None = None
    android_version: str | None = None
    api_level: int | None = None
    abi: str | None = None
    density: int | None = None
    is_test_profile: bool = False


@dataclass(slots=True)
class ApkInfo:
    file_path: Path
    file_hash: str
    package_name: str
    version_name: str | None = None
    version_code: int | None = None
    target_sdk: int | None = None
    min_sdk: int | None = None
    compile_sdk: int | None = None
    size_bytes: int = 0
    permissions: list[str] = field(default_factory=list)
    activities: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    receivers: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    signature_schemes: list[int] = field(default_factory=list)
    certificate_fingerprint_sha256: str | None = None
    analyzed_at: datetime | None = None


@dataclass(slots=True)
class TestStepResult:
    name: str
    passed: bool
    duration_ms: int
    detail: str = ""


@dataclass(slots=True)
class TestRun:
    apk: ApkInfo
    device_serial: str
    profile_name: str
    started_at: datetime
    steps: list[TestStepResult] = field(default_factory=list)
    verdict: Verdict = Verdict.PASS
    duration_ms: int = 0
    log_excerpt: str | None = None
    screenshot_path: Path | None = None


@dataclass(slots=True)
class Finding:
    rule_id: str
    severity: Severity
    file_path: Path
    match_hash: str
    redacted: str
    line_number: int | None = None
    suppressed: bool = False
    suppress_note: str | None = None


@dataclass(slots=True)
class ScanResult:
    target_type: str  # project | apk
    target_path: Path
    started_at: datetime
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    duration_ms: int = 0


@dataclass(slots=True)
class ReleaseCheck:
    category: str
    passed: bool
    weight: int
    blocking: bool
    detail: str = ""


@dataclass(slots=True)
class GateResult:
    checks: list[ReleaseCheck]
    score: int
    verdict: GateVerdict
    override_note: str | None = None
