"""OrganizerService (Smart File Organizer) — Section 6.12. Rule engine (first match
wins, ordered by priority) evaluates extension, filename pattern, magic bytes, size,
and age. Every batch operation writes an undo journal before moving anything;
deletions go through send2trash, never os.remove, so OS-level recovery stays
available as a second layer.
"""

from __future__ import annotations

import json
import tomllib
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from send2trash import send2trash

from droiddesk.infra.hashing import find_duplicates


@dataclass(slots=True)
class OrganizeRule:
    name: str
    destination: str
    priority: int
    match_ext: list[str] | None = None
    match_name: str | None = None
    older_than_days: int | None = None


@dataclass(slots=True)
class PlannedMove:
    source: Path
    destination: Path


class OrganizerService(QObject):
    progress = Signal(int, int)
    plan_ready = Signal(list)
    finished = Signal(str)

    def __init__(self, journal_dir: Path) -> None:
        super().__init__()
        self._journal_dir = journal_dir
        self._journal_dir.mkdir(parents=True, exist_ok=True)

    def load_rules(self, rules_path: Path) -> list[OrganizeRule]:
        with rules_path.open("rb") as f:
            data = tomllib.load(f)
        rules = [OrganizeRule(**entry) for entry in data.get("rules", [])]
        return sorted(rules, key=lambda r: r.priority)

    def plan(self, source_dir: Path, rules: list[OrganizeRule]) -> list[PlannedMove]:
        # TODO(Phase 6): evaluate each file against `rules`, first match wins,
        # using content sniffing (magic bytes) in addition to extension/name.
        raise NotImplementedError

    def find_duplicates(self, files: list[Path]) -> dict[str, list[Path]]:
        return find_duplicates(files)

    def apply(self, moves: list[PlannedMove]) -> str:
        batch_id = str(uuid.uuid4())
        journal_path = self._journal_dir / f"{batch_id}.json"
        journal_path.write_text(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "timestamp": datetime.now().isoformat(),
                    "moves": [
                        {"source": str(m.source), "destination": str(m.destination), "done": False}
                        for m in moves
                    ],
                }
            )
        )
        # TODO(Phase 6): perform the moves, updating the journal entry-by-entry
        # as each completes, so a crash mid-batch is recoverable on next launch.
        raise NotImplementedError

    def undo(self, batch_id: str) -> None:
        # TODO(Phase 6): replay the journal in reverse.
        raise NotImplementedError

    def trash(self, path: Path) -> None:
        send2trash(str(path))

    def recover_incomplete_batches(self) -> list[str]:
        return [p.stem for p in self._journal_dir.glob("*.json")]
