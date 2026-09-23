"""Security scan suppression management.

Persistent suppression records stored in .droiddesk/suppressions.toml.
A suppression is bound to rule_id, file path, and match_hash; if the underlying
matched content changes, match_hash changes and the suppression automatically expires.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from droiddesk.core.models import Finding


@dataclass(slots=True)
class Suppression:
    rule_id: str
    file: str  # relative posix path string
    match_hash: str
    reason: str
    created_at: str | None = None


class SuppressionManager:
    """Manages reading, writing, and applying suppressions for a project."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._suppressions_file = root / ".droiddesk" / "suppressions.toml"

    def load(self) -> list[Suppression]:
        """Load active suppressions from .droiddesk/suppressions.toml."""
        if not self._suppressions_file.is_file():
            return []
        try:
            with self._suppressions_file.open("rb") as f:
                data = tomllib.load(f)
            return [
                Suppression(
                    rule_id=str(s["rule_id"]),
                    file=str(s["file"]),
                    match_hash=str(s["match_hash"]),
                    reason=str(s.get("reason", "")),
                    created_at=s.get("created_at"),
                )
                for s in data.get("suppressions", [])
                if "rule_id" in s and "file" in s and "match_hash" in s
            ]
        except Exception:
            return []

    def save(self, suppressions: list[Suppression]) -> None:
        """Serialize suppressions back to .droiddesk/suppressions.toml."""
        self._suppressions_file.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# DroidDesk security scan suppressions",
            "# Automatically maintained. Manual edits are preserved.",
            "",
        ]
        for s in suppressions:
            lines.append("[[suppressions]]")
            lines.append(f'rule_id = "{s.rule_id}"')
            lines.append(f'file = "{s.file}"')
            lines.append(f'match_hash = "{s.match_hash}"')
            escaped_reason = s.reason.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'reason = "{escaped_reason}"')
            if s.created_at:
                lines.append(f'created_at = "{s.created_at}"')
            lines.append("")
        self._suppressions_file.write_text("\n".join(lines), encoding="utf-8")

    def _relative_file_path(self, path: Path) -> str:
        try:
            return path.relative_to(self._root).as_posix()
        except ValueError:
            return path.as_posix()

    def is_suppressed(self, finding: Finding) -> tuple[bool, str | None]:
        """Check if a finding matches an existing suppression record."""
        rel_path = self._relative_file_path(finding.file_path)
        for s in self.load():
            if (
                s.rule_id == finding.rule_id
                and s.file == rel_path
                and s.match_hash == finding.match_hash
            ):
                return True, s.reason
        return False, None

    def add_suppression(self, finding: Finding, reason: str) -> Suppression:
        """Add or update a suppression for the specified finding."""
        from datetime import UTC, datetime

        rel_path = self._relative_file_path(finding.file_path)
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        new_sup = Suppression(
            rule_id=finding.rule_id,
            file=rel_path,
            match_hash=finding.match_hash,
            reason=reason,
            created_at=now,
        )

        current = self.load()
        filtered = [
            s
            for s in current
            if not (
                s.rule_id == new_sup.rule_id
                and s.file == new_sup.file
                and s.match_hash == new_sup.match_hash
            )
        ]
        filtered.append(new_sup)
        self.save(filtered)
        return new_sup

    def apply_suppressions(self, findings: list[Finding]) -> list[Finding]:
        """Apply active suppressions to a list of findings in-place."""
        suppressions = self.load()
        sup_lookup: dict[tuple[str, str, str], str] = {
            (s.rule_id, s.file, s.match_hash): s.reason for s in suppressions
        }

        for f in findings:
            rel_path = self._relative_file_path(f.file_path)
            key = (f.rule_id, rel_path, f.match_hash)
            if key in sup_lookup:
                f.suppressed = True
                f.suppress_note = sup_lookup[key]
        return findings
