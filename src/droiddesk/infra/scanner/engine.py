"""Scanner engine: rule loading, Aho-Corasick pre-filter, compiled regex matching,
entropy scoring, dedup. See Section 6.5 (mechanism) and Section 8.2 (performance).

Performance rules that keep 200+ patterns fast over a project tree:
  - Pre-filter with Aho-Corasick over each rule's fixed literal prefix; only files
    with a literal hit proceed to full regex evaluation.
  - Skip build/, .git/, node_modules/, .gradle/, .dart_tool/, and binary content
    (null byte in the first 8 KB) by default.
  - Cap file size at 10 MB by default; skip larger files with a note.
  - Compile all patterns once at construction, never inside the per-file loop.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import ahocorasick
import regex

from droiddesk.core.models import Finding
from droiddesk.core.severity import Severity

_DEFAULT_EXCLUDED_DIRS = {"build", ".git", "node_modules", ".gradle", ".dart_tool", ".venv"}
_DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024
_BINARY_SNIFF_BYTES = 8192


@dataclass(slots=True)
class Rule:
    id: str
    severity: Severity
    literal_prefixes: list[str]
    pattern: regex.Pattern[str] | None
    description: str = ""


def _load_rules_file(path: Path) -> list[Rule]:
    with path.open("rb") as f:
        data = tomllib.load(f)

    rules: list[Rule] = []
    for entry in data.get("rules", []):
        pattern_text = entry.get("pattern") or ""
        compiled = regex.compile(pattern_text) if pattern_text else None
        rules.append(
            Rule(
                id=entry["id"],
                severity=Severity(entry.get("severity", "review")),
                literal_prefixes=entry.get("literal_prefixes", []),
                pattern=compiled,
                description=entry.get("description", ""),
            )
        )
    return rules


class ScannerEngine:
    def __init__(
        self,
        rule_files: list[Path] | None = None,
        excluded_dirs: set[str] | None = None,
        max_file_size: int = _DEFAULT_MAX_FILE_SIZE,
    ) -> None:
        rule_files = rule_files or [
            Path(__file__).parent / "rules.toml",
            Path(__file__).parent / "android.toml",
        ]
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

    def _should_skip(self, path: Path) -> bool:
        if any(part in self._excluded_dirs for part in path.parts):
            return True
        if path.stat().st_size > self._max_file_size:
            return True
        if self._is_binary(path):
            return True
        return False

    def scan_file(self, path: Path) -> list[Finding]:
        if self._should_skip(path):
            return []

        text = path.read_text(encoding="utf-8", errors="replace")
        matched_rule_ids = {rule_id for _, (_, rule_id) in self._automaton.iter(text)}
        if not matched_rule_ids:
            return []

        findings: list[Finding] = []
        for rule in self._rules:
            if rule.id not in matched_rule_ids or rule.pattern is None:
                continue
            for match in rule.pattern.finditer(text):
                line_number = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        rule_id=rule.id,
                        severity=rule.severity,
                        file_path=path,
                        line_number=line_number,
                        match_hash=_hash_line(match.group(0)),
                        redacted=_redact(match.group(0)),
                    )
                )
        return findings

    def scan_tree(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        for path in root.rglob("*"):
            if path.is_file():
                findings.extend(self.scan_file(path))
        return _dedup(findings)


def _hash_line(text: str) -> str:
    import xxhash

    return xxhash.xxh3_64(text.encode("utf-8")).hexdigest()


def _redact(text: str, keep: int = 4) -> str:
    if len(text) <= keep * 2:
        return "*" * len(text)
    return f"{text[:keep]}{'*' * (len(text) - keep * 2)}{text[-keep:]}"


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
