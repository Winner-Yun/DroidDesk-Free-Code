"""File organization and batch renaming service with preview and undo journal."""

from __future__ import annotations

import fnmatch
import json
import logging
import re
import shutil
import tomllib
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal
from send2trash import send2trash  # type: ignore[import-untyped]

from droiddesk.infra.hashing import find_duplicates

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OrganizeRule:
    name: str
    destination: str
    priority: int
    match_ext: list[str] | None = None
    match_name: str | None = None
    older_than_days: int | None = None
    magic_bytes: list[str] | None = None
    min_size_bytes: int | None = None
    max_size_bytes: int | None = None


@dataclass(slots=True)
class PlannedMove:
    source: Path
    destination: Path
    rule_name: str = ""
    suggested_name: str = ""
    reason: str = ""


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

    def suggest_rename(self, file_path: Path, style: str = "smart_clean") -> tuple[str, str]:
        """Analyze filename, metadata, and extension to generate a smart suggested rename.

        Returns (suggested_filename, explanation_of_changes).
        """
        stem = file_path.stem
        orig_stem = stem
        ext = file_path.suffix
        reasons: list[str] = []

        # URL decode
        decoded = urllib.parse.unquote(stem)
        if decoded != stem:
            reasons.append("Decoded URL")
            stem = decoded

        # Strip duplicate and copy artifacts
        prev_copy = ""
        s_copy = stem
        while s_copy != prev_copy:
            prev_copy = s_copy
            s_copy = re.sub(r"\s*\(\d+\)$", "", s_copy)
            s_copy = re.sub(r"[\s_-]*\(?copy(\s*\d+)?\)?$", "", s_copy, flags=re.IGNORECASE)
            s_copy = re.sub(r"[\s_-]*\(?duplicate(\s*\d+)?\)?$", "", s_copy, flags=re.IGNORECASE)
            s_copy = re.sub(r"^copy\s+of\s+", "", s_copy, flags=re.IGNORECASE)
        if s_copy != stem:
            reasons.append("Trimmed copy suffix")
            stem = s_copy

        # Clean media quality and scene tags
        media_clean = re.sub(
            r"[\.\[\(_-](1080p|720p|4k|2160p|bluray|web-?dl|webrip|hdtv|x264|x265|hevc)[\.\]\)_-]?",
            "",
            stem,
            flags=re.IGNORECASE,
        )
        if media_clean != stem:
            reasons.append("Stripped media tags")
            stem = media_clean

        # Clean common APK build markers
        if ext.lower() in (".apk", ".aab", ".xapk"):
            apk_clean = re.sub(r"[-_](unsigned|aligned|signed)", "", stem, flags=re.IGNORECASE)
            if apk_clean != stem:
                reasons.append("Cleaned APK tags")
                stem = apk_clean

        # Standardize screenshot and camera timestamp patterns
        m_shot = re.match(
            r"^(Screenshot|IMG|PXL|VID)[_-](\d{4})[-_]?(\d{2})[-_]?(\d{2})[\s_-]+(\d{2})[-_\s]?(\d{2})[-_\s]?(\d{2})(.*)$",
            stem,
            re.IGNORECASE,
        )
        if m_shot:
            prefix, y, mo, d, h, mi, s, rest = m_shot.groups()
            stem = f"{prefix.lower()}_{y}-{mo}-{d}_{h}{mi}{s}{rest}"
            reasons.append("Standardized date")

        # Apply selected formatting style
        if style == "kebab":
            stem = re.sub(r"[_\s.]+", "-", stem)
            stem = re.sub(r"[^a-zA-Z0-9-]", "", stem)
            stem = re.sub(r"-+", "-", stem).strip("-").lower()
            reasons.append("kebab-case")
        elif style == "snake":
            stem = re.sub(r"[-\s.]+", "_", stem)
            stem = re.sub(r"[^a-zA-Z0-9_]", "", stem)
            stem = re.sub(r"_+", "_", stem).strip("_").lower()
            reasons.append("snake_case")
        elif style == "date_prefix":
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                date_str = mtime.strftime("%Y-%m-%d")
            except OSError:
                date_str = datetime.now().strftime("%Y-%m-%d")
            stem = re.sub(r"^\d{4}[-_]\d{2}[-_]\d{2}[-_]?", "", stem)
            clean_stem = re.sub(r"[\s_]+", "_", stem).strip("_")
            stem = f"{date_str}_{clean_stem}"
            reasons.append("Date prefix")
        elif style == "title":
            stem = re.sub(r"[_\s-]+", " ", stem).strip().title()
            reasons.append("Title Case")
        else:  # "smart_clean"
            if ext.lower() in (".pdf", ".docx", ".xlsx", ".pptx", ".txt") and "_" in stem:
                stem = re.sub(r"[_\s-]+", " ", stem).strip().title()
                reasons.append("Cleaned title")
            else:
                stem = re.sub(r"[ \t]+", " ", stem)
                stem = re.sub(r"_+", "_", stem)
                stem = re.sub(r"-+", "-", stem)
                # Strip out invalid Windows filename punctuation
                for ch in ['"', "*", "/", ":", "<", ">", "?", "\\", "|", "`", "~", "^"]:
                    stem = stem.replace(ch, "")
                stem = stem.strip(" ._-")
                if stem != orig_stem and not reasons:
                    reasons.append("Cleaned separators")

        if not stem:
            stem = orig_stem

        final_name = f"{stem}{ext}"
        explanation = ", ".join(reasons) if reasons else "Already clean"
        return final_name, explanation

    def plan(
        self,
        source_dir: Path,
        rules: list[OrganizeRule] | None = None,
        style: str = "smart_clean",
        organize_into_folders: bool = False,
    ) -> list[PlannedMove]:
        """Scan any folder, inspect all file extensions, and generate suggested renames."""
        sorted_rules = sorted(rules, key=lambda r: r.priority) if rules else []
        planned: list[PlannedMove] = []
        if not source_dir.is_dir():
            return planned

        now = datetime.now()
        files = [p for p in source_dir.iterdir() if p.is_file()]
        total = len(files)

        # Track filenames to avoid collisions
        used_target_names: set[str] = {f.name.lower() for f in files}

        for idx, file_path in enumerate(files):
            self.progress.emit(idx, total)

            suggested_name, reason = self.suggest_rename(file_path, style=style)

            # If not organizing into subfolders and the file is already clean, do not suggest rename
            if not organize_into_folders and (
                suggested_name == file_path.name or reason == "Already clean"
            ):
                continue

            # Determine destination folder
            dest_folder = source_dir
            rule_name = reason
            if organize_into_folders and sorted_rules:
                matched_rule = self._evaluate_file(file_path, sorted_rules, now)
                if matched_rule is not None:
                    dest_folder = source_dir / matched_rule.destination
                    rule_name = f"{matched_rule.name} - {reason}"
                else:
                    dest_folder = source_dir / "Other"
                    rule_name = f"Other - {reason}"

            # Avoid collision with other planned targets in this batch or existing files
            candidate_name = suggested_name
            collision_idx = 1
            while (
                candidate_name.lower() in used_target_names
                and candidate_name.lower() != file_path.name.lower()
            ):
                p_cand = Path(candidate_name)
                candidate_name = f"{p_cand.stem}_{collision_idx}{p_cand.suffix}"
                collision_idx += 1
            used_target_names.add(candidate_name.lower())
            suggested_name = candidate_name

            target_path = dest_folder / suggested_name

            # If organizing into folders, skip if already in the target folder and name unchanged
            if organize_into_folders and target_path == file_path:
                continue

            planned.append(
                PlannedMove(
                    source=file_path,
                    destination=target_path,
                    rule_name=rule_name,
                    suggested_name=suggested_name,
                    reason=reason,
                )
            )

        self.progress.emit(total, total)
        self.plan_ready.emit(planned)
        return planned

    def _evaluate_file(
        self, file_path: Path, rules: list[OrganizeRule], now: datetime
    ) -> OrganizeRule | None:
        try:
            stat = file_path.stat()
            file_size = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime)
        except OSError:
            return None

        header_bytes: bytes | None = None

        for rule in rules:
            if rule.match_ext is not None:
                exts = [e.lower().lstrip(".") for e in rule.match_ext]
                file_ext = file_path.suffix.lower().lstrip(".")
                if file_ext not in exts:
                    continue

            if rule.match_name is not None and not fnmatch.fnmatch(
                file_path.name.lower(), rule.match_name.lower()
            ):
                continue

            if rule.older_than_days is not None:
                age_days = (now - mtime).days
                if age_days < rule.older_than_days:
                    continue

            if rule.min_size_bytes is not None and file_size < rule.min_size_bytes:
                continue
            if rule.max_size_bytes is not None and file_size > rule.max_size_bytes:
                continue

            if rule.magic_bytes:
                if header_bytes is None:
                    try:
                        with file_path.open("rb") as f:
                            header_bytes = f.read(64)
                    except OSError:
                        header_bytes = b""

                magic_matched = False
                for mb in rule.magic_bytes:
                    try:
                        expected = bytes.fromhex(mb.replace(" ", ""))
                        if header_bytes.startswith(expected):
                            magic_matched = True
                            break
                    except ValueError:
                        continue
                if not magic_matched:
                    continue

            return rule

        return None

    def find_duplicates(self, files: list[Path]) -> dict[str, list[Path]]:
        return find_duplicates(files)

    def apply(self, moves: list[PlannedMove], batch_id: str | None = None) -> str:
        """Execute planned renames/moves with a crash-resilient journal.

        If batch_id is provided, appends to the existing batch journal, enabling
        one-by-one renames to be grouped into the same undo session.
        """
        if not batch_id:
            batch_id = str(uuid.uuid4())

        journal_path = self._journal_dir / f"{batch_id}.json"

        existing_moves: list[dict[str, Any]] = []
        if journal_path.is_file():
            try:
                loaded = json.loads(journal_path.read_text(encoding="utf-8"))
                if isinstance(loaded.get("moves"), list):
                    existing_moves = loaded["moves"]
            except Exception:
                pass

        new_moves_data = [
            {
                "source": str(m.source),
                "destination": str(m.destination),
                "suggested_name": m.suggested_name,
                "rule": m.rule_name,
                "done": False,
            }
            for m in moves
        ]

        all_moves_data = existing_moves + new_moves_data

        journal_data: dict[str, Any] = {
            "batch_id": batch_id,
            "timestamp": datetime.now().isoformat(),
            "moves": all_moves_data,
        }

        journal_path.write_text(json.dumps(journal_data, indent=2), encoding="utf-8")

        total = len(moves)
        for idx, (move, entry) in enumerate(zip(moves, new_moves_data, strict=True)):
            self.progress.emit(idx, total)
            if not move.source.exists():
                logger.warning("Rename source does not exist: %s", move.source)
                continue

            try:
                move.destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(move.source), str(move.destination))
                entry["done"] = True
                journal_path.write_text(json.dumps(journal_data, indent=2), encoding="utf-8")
            except Exception as exc:
                logger.error("Failed to rename %s -> %s: %s", move.source, move.destination, exc)
                journal_path.write_text(json.dumps(journal_data, indent=2), encoding="utf-8")
                raise RuntimeError(
                    f"Organizer batch interrupted: failed to rename {move.source.name}: {exc}"
                ) from exc

        self.progress.emit(total, total)
        self.finished.emit(batch_id)
        return batch_id

    def undo(self, batch_id: str) -> None:
        """Reverse completed renames/moves in a batch journal in LIFO order."""
        journal_path = self._journal_dir / f"{batch_id}.json"
        if not journal_path.is_file():
            raise FileNotFoundError(f"Journal batch {batch_id} not found at {journal_path}")

        data = json.loads(journal_path.read_text(encoding="utf-8"))
        raw_moves = data.get("moves", [])
        if not isinstance(raw_moves, list):
            return

        completed = [m for m in raw_moves if isinstance(m, dict) and m.get("done") is True]
        total = len(completed)

        for idx, entry in enumerate(reversed(completed)):
            self.progress.emit(idx, total)
            src = Path(entry["source"])
            dest = Path(entry["destination"])

            if not dest.exists():
                logger.warning("Undo destination file not found: %s", dest)
                continue

            if src.exists():
                logger.warning("Undo source location already occupied: %s", src)
                continue

            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(src))
            entry["done"] = False
            journal_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        self.progress.emit(total, total)
        self.finished.emit(batch_id)

    def trash(self, path: Path) -> None:
        send2trash(str(path))

    def recover_incomplete_batches(self) -> list[str]:
        return [p.stem for p in self._journal_dir.glob("*.json")]
