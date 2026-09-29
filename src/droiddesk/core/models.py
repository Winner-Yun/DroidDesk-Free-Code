"""Core domain models for devices, APK information, findings, and test runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from droiddesk.core.severity import Severity, Verdict


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
    certificate_fingerprint_sha1: str | None = None
    certificate_fingerprint_md5: str | None = None
    certificate_dn: str | None = None
    signature_verified: bool = False
    signature_source: str | None = None
    debuggable: bool | None = None
    analyzed_at: datetime | None = None


@dataclass(slots=True)
class TestStepResult:
    __test__ = False

    name: str
    passed: bool
    duration_ms: int
    detail: str = ""


@dataclass(slots=True)
class TestRun:
    __test__ = False

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
class Project:
    name: str
    root_path: Path
    package_name: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    last_opened: datetime | None = None


@dataclass(slots=True)
class BuildRecord:
    command: str
    environment: str
    started_at: datetime
    project_id: int | None = None
    gate_score: int | None = None
    gate_verdict: str | None = None
    overridden: bool = False
    override_note: str | None = None
    exit_code: int | None = None
    id: int | None = None


@dataclass(slots=True)
class ScreenConfig:
    max_size: int = 1080
    bit_rate: int = 8
    max_fps: int = 60
    stay_awake: bool = True
    turn_screen_off: bool = False
    forward_audio: bool = False
    show_touches: bool = False
    always_on_top: bool = True
    fullscreen: bool = False
    embedded: bool = False
    record_file: Path | None = None

