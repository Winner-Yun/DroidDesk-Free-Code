"""Scanner engine: rule loading, Aho-Corasick pre-filter, regex matching, and entropy scoring."""

from __future__ import annotations

import fnmatch
import os
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import ahocorasick  # type: ignore[import-not-found]
import regex

from droiddesk.core.models import Finding
from droiddesk.core.severity import Severity
from droiddesk.infra.scanner.entropy import looks_like_credential
from droiddesk.infra.scanner.util import hash_match, redact_secret

_DEFAULT_EXCLUDED_DIRS = {
    "build",
    ".git",
    "node_modules",
    ".gradle",
    ".dart_tool",
    ".venv",
    "dist",
    ".idea",
    "__pycache__",
}
_DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024
_BINARY_SNIFF_BYTES = 8192

# Pattern to capture variable/key-value assignments for entropy scanning
_ASSIGNMENT_PATTERNS = regex.compile(
    r"""(?:([a-zA-Z_][a-zA-Z0-9_.-]*)\s*[:=]\s*["']([^"'\r\n]+)["']|"""
    r"""<string\s+[^>]*name=["']([^"']+)["'][^>]*>([^<]+)</string>|"""
    r"""([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([^\s\r\n"']+))"""
)

# AIzaSy key regex pattern
_AIZASY_PATTERN = regex.compile(r"\bAIzaSy[0-9A-Za-z_-]{30,45}\b")


@dataclass(slots=True)
class Rule:
    id: str
    severity: Severity
    literal_prefixes: list[str] = field(default_factory=list)
    pattern: regex.Pattern[str] | None = None
    match_name: str | None = None
    match_ext: list[str] = field(default_factory=list)
    description: str = ""


def _load_rules_file(path: Path) -> list[Rule]:
    with path.open("rb") as f:
        data = tomllib.load(f)

    rules: list[Rule] = []
    for entry in data.get("rules", []):
        pattern_text = entry.get("pattern") or ""
        compiled = regex.compile(pattern_text) if pattern_text else None

        match_name = entry.get("match_name")
        match_ext_val = entry.get("match_ext", [])
        match_ext = [match_ext_val] if isinstance(match_ext_val, str) else list(match_ext_val)

        rules.append(
            Rule(
                id=entry["id"],
                severity=Severity(entry.get("severity", "review")),
                literal_prefixes=entry.get("literal_prefixes", []),
                pattern=compiled,
                match_name=match_name,
                match_ext=[ext.lower() for ext in match_ext],
                description=entry.get("description", ""),
            )
        )
    return rules


def _default_rule_files() -> list[Path]:
    candidates: list[Path] = [Path(__file__).resolve().parent]
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "droiddesk" / "infra" / "scanner")
        candidates.append(Path(sys._MEIPASS) / "infra" / "scanner")

    for base in candidates:
        r = base / "rules.toml"
        a = base / "android.toml"
        if r.is_file() and a.is_file():
            return [r, a]
    return [Path(__file__).parent / "rules.toml", Path(__file__).parent / "android.toml"]


class ScannerEngine:
    def __init__(
        self,
        rule_files: list[Path] | None = None,
        excluded_dirs: set[str] | None = None,
        max_file_size: int = _DEFAULT_MAX_FILE_SIZE,
    ) -> None:
        rule_files = rule_files or _default_rule_files()
        self._rules: list[Rule] = []
        for rule_file in rule_files:
            self._rules.extend(_load_rules_file(rule_file))

        self._excluded_dirs = excluded_dirs or _DEFAULT_EXCLUDED_DIRS
        self._max_file_size = max_file_size
        self._automaton = self._build_automaton()

    def _build_automaton(self) -> ahocorasick.Automaton:
        automaton = ahocorasick.Automaton()
        for rule in self._rules:
            for literal in rule.literal_prefixes:
                automaton.add_word(literal, (literal, rule.id))
        automaton.make_automaton()
        return automaton

    def _is_binary(self, path: Path) -> bool:
        with path.open("rb") as f:
            chunk = f.read(_BINARY_SNIFF_BYTES)
        return b"\x00" in chunk

    def should_skip(self, path: Path) -> bool:
        if any(part in self._excluded_dirs for part in path.parts):
            return True
        try:
            if path.stat().st_size > self._max_file_size:
                return True
        except OSError:
            return True
        return False

    def scan_file(self, path: Path) -> list[Finding]:
        if self.should_skip(path):
            return []

        findings: list[Finding] = []
        filename = path.name
        file_ext = path.suffix.lower()

        # Extension-based rules (keystores and certificates)
        for rule in self._rules:
            if (
                rule.match_ext
                and file_ext in rule.match_ext
                and not rule.literal_prefixes
                and rule.pattern is None
            ):
                findings.append(
                    Finding(
                        rule_id=rule.id,
                        severity=rule.severity,
                        file_path=path,
                        line_number=None,
                        match_hash=hash_match(filename),
                        redacted=f"[Signing Key: {filename}]",
                    )
                )

        # If binary, stop here; we cannot evaluate textual content
        try:
            if self._is_binary(path):
                return findings
        except OSError:
            return findings

        # Read text content for content and filename+content rules
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return findings

        # Filename-based rules
        for rule in self._rules:
            if rule.match_name and fnmatch.fnmatch(filename, rule.match_name):
                # If rule has literal_prefixes, require a prefix match in content
                if rule.literal_prefixes:
                    for prefix in rule.literal_prefixes:
                        if prefix in text:
                            # Find first line matching the prefix
                            for line_idx, line in enumerate(text.splitlines()):
                                if prefix in line:
                                    findings.append(
                                        Finding(
                                            rule_id=rule.id,
                                            severity=rule.severity,
                                            file_path=path,
                                            line_number=line_idx + 1,
                                            match_hash=hash_match(line.strip()),
                                            redacted=redact_secret(line.strip()),
                                        )
                                    )
                                    break
                            break
                elif rule.pattern is None:
                    # File-presence rule (e.g. google-services.json)
                    findings.append(
                        Finding(
                            rule_id=rule.id,
                            severity=rule.severity,
                            file_path=path,
                            line_number=None,
                            match_hash=hash_match(filename),
                            redacted=f"[Config File: {filename}]",
                        )
                    )

        # Literal prefix and pattern matching via Aho-Corasick
        matched_rule_ids = {rule_id for _, (_, rule_id) in self._automaton.iter(text)}

        # Evaluate AIzaSy Google / Firebase API Key Disambiguation if AIzaSy matched
        if (
            any(
                rid in matched_rule_ids
                for rid in (
                    "android-maps-api-key",
                    "android-firebase-legacy-token",
                    "firebase-api-key",
                    "google-api-key",
                )
            )
            or "AIzaSy" in text
        ):
            for match in _AIZASY_PATTERN.finditer(text):
                val = match.group(0)
                line_number = text.count("\n", 0, match.start()) + 1

                # Extract line text for attribute / variable detection
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                if line_end == -1:
                    line_end = len(text)
                line_text = text[line_start:line_end]

                var_name = ""
                # XML string resource or meta-data name:
                xml_match = regex.search(
                    r'(?:name|android:name)\s*=\s*["\']([^"\']+)["\']', line_text
                )
                if xml_match:
                    var_name = xml_match.group(1)
                else:
                    # JSON key or code assignment:
                    json_match = regex.search(
                        r'["\']([a-zA-Z0-9_.-]+)["\']\s*:\s*["\']?' + regex.escape(val[:8]),
                        line_text,
                    )
                    if json_match:
                        var_name = json_match.group(1)
                    else:
                        code_match = regex.search(
                            r'([a-zA-Z_][a-zA-Z0-9_.-]*)\s*[:=]\s*["\']?' + regex.escape(val[:8]),
                            line_text,
                        )
                        if code_match:
                            var_name = code_match.group(1)

                var_lower = var_name.lower().strip()

                start_ctx = max(0, match.start() - 300)
                end_ctx = min(len(text), match.end() + 300)
                context_slice = text[start_ctx:end_ctx].lower()
                path_lower = str(path).lower()

                # Disambiguate: Legacy Token vs Maps API Key vs Firebase API Key vs General
                is_firebase_legacy = any(
                    w in var_lower or w in context_slice
                    for w in ("legacy_token", "database_secret", "firebase_secret")
                )

                is_maps = (
                    any(w in var_lower for w in ("map", "geo", "places", "directions", "location"))
                    or any(
                        w in context_slice
                        for w in (
                            "com.google.android.geo",
                            "geo.api_key",
                            "maps_api_key",
                            "google_maps",
                        )
                    )
                ) and not any(w in var_lower for w in ("firebase", "fcm"))

                is_firebase = (
                    any(
                        w in var_lower
                        for w in (
                            "firebase",
                            "fcm",
                            "google_api_key",
                            "google_app_id",
                            "crashlytics",
                            "firestore",
                        )
                    )
                    or "google-services" in path_lower
                    or "firebase" in path_lower
                    or any(
                        w in context_slice
                        for w in (
                            "firebase",
                            "google-services",
                            "google_app_id",
                            "firebase_database_url",
                            "gcm_defaultsenderid",
                            "default_web_client_id",
                            "google_storage_bucket",
                        )
                    )
                )

                if is_firebase_legacy:
                    rule_id = "android-firebase-legacy-token"
                    severity = Severity.HIGH
                elif is_maps:
                    rule_id = "android-maps-api-key"
                    severity = Severity.NEEDS_REVIEW
                elif is_firebase:
                    rule_id = "firebase-api-key"
                    severity = Severity.NEEDS_REVIEW
                else:
                    rule_id = "google-api-key"
                    severity = Severity.NEEDS_REVIEW

                val_hash = hash_match(val)
                already_matched = any(
                    f.match_hash == val_hash and f.line_number == line_number for f in findings
                )
                if not already_matched:
                    findings.append(
                        Finding(
                            rule_id=rule_id,
                            severity=severity,
                            file_path=path,
                            line_number=line_number,
                            match_hash=val_hash,
                            redacted=redact_secret(val),
                        )
                    )

        # Compiled pattern rules
        for rule in self._rules:
            if rule.pattern is None:
                continue
            if rule.literal_prefixes and rule.id not in matched_rule_ids:
                continue

            for match in rule.pattern.finditer(text):
                line_number = text.count("\n", 0, match.start()) + 1
                matched_val = match.group(0)
                findings.append(
                    Finding(
                        rule_id=rule.id,
                        severity=rule.severity,
                        file_path=path,
                        line_number=line_number,
                        match_hash=hash_match(matched_val),
                        redacted=redact_secret(matched_val),
                    )
                )

        # Entropy heuristic checks
        entropy_rule = next(
            (r for r in self._rules if r.id == "high-entropy-credential-string"), None
        )
        if entropy_rule is not None:
            # Check lines for candidate credential assignments
            lines = text.splitlines()
            for line_idx, line in enumerate(lines):
                for match in _ASSIGNMENT_PATTERNS.finditer(line):
                    groups = match.groups()
                    var_name = groups[0] or groups[2] or groups[4] or ""
                    val = groups[1] or groups[3] or groups[5] or ""
                    var_name = var_name.strip()
                    val = val.strip()

                    if looks_like_credential(var_name, val):
                        # Avoid duplicating if already matched by another rule
                        val_hash = hash_match(val)
                        if not any(f.match_hash == val_hash for f in findings):
                            v_lower = var_name.lower()
                            if any(w in v_lower for w in ("firebase", "fcm")):
                                e_rule_id = "firebase-api-key"
                            elif any(w in v_lower for w in ("map", "geo", "places")):
                                e_rule_id = "android-maps-api-key"
                            elif "aws" in v_lower:
                                e_rule_id = "aws-access-key-id"
                            elif var_name:
                                e_rule_id = f"custom-{var_name.lower().replace('_', '-')}"
                            else:
                                e_rule_id = entropy_rule.id

                            findings.append(
                                Finding(
                                    rule_id=e_rule_id,
                                    severity=entropy_rule.severity,
                                    file_path=path,
                                    line_number=line_idx + 1,
                                    match_hash=val_hash,
                                    redacted=redact_secret(val),
                                )
                            )

        return findings

    def scan_tree(
        self, root: Path, is_cancelled: Callable[[], bool] | None = None
    ) -> list[Finding]:
        findings: list[Finding] = []
        for dirpath, dirnames, filenames in os.walk(root):
            if is_cancelled and is_cancelled():
                break
            dirnames[:] = [
                d for d in dirnames if d not in self._excluded_dirs and not d.startswith(".")
            ]
            for filename in filenames:
                if is_cancelled and is_cancelled():
                    break
                file_path = Path(dirpath) / filename
                findings.extend(self.scan_file(file_path))
        return _dedup(findings)


# Aliases for backwards compatibility
_hash_line = hash_match
_redact = redact_secret


def _dedup(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[Path, int | None, str]] = set()
    deduped: list[Finding] = []
    for finding in findings:
        key = (finding.file_path, finding.line_number, finding.rule_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped
