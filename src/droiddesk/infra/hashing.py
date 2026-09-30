"""Content hashing and multi-tier duplicate file detection."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import xxhash
from PySide6.QtCore import QObject, QRunnable, Signal

_PARTIAL_READ_BYTES = 8 * 1024


def hash_file(path: Path) -> str:
    """Calculate fast full-content xxhash for an artifact or file."""
    hasher = xxhash.xxh3_64()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_partial(path: Path) -> str:
    """First and last 8 KB only - tier 2 of duplicate detection."""
    hasher = xxhash.xxh3_64()
    size = path.stat().st_size
    with path.open("rb") as f:
        hasher.update(f.read(_PARTIAL_READ_BYTES))
        if size > _PARTIAL_READ_BYTES:
            f.seek(max(size - _PARTIAL_READ_BYTES, 0))
            hasher.update(f.read(_PARTIAL_READ_BYTES))
    return hasher.hexdigest()


def find_duplicates(paths: list[Path]) -> dict[str, list[Path]]:
    """Three-tier duplicate detection, run synchronously. See HashTask for the
    QThreadPool-driven, cancellable, progress-reporting variant used by the UI.
    """
    by_size: dict[int, list[Path]] = defaultdict(list)
    for path in paths:
        by_size[path.stat().st_size].append(path)

    duplicates: dict[str, list[Path]] = defaultdict(list)
    for size_group in by_size.values():
        if len(size_group) < 2:
            continue
        by_partial: dict[str, list[Path]] = defaultdict(list)
        for path in size_group:
            by_partial[hash_partial(path)].append(path)
        for partial_group in by_partial.values():
            if len(partial_group) < 2:
                continue
            for path in partial_group:
                duplicates[hash_file(path)].append(path)

    return {digest: group for digest, group in duplicates.items() if len(group) > 1}


class TaskSignals(QObject):
    progress = Signal(int, int)
    finished = Signal(dict)
    cancelled = Signal()


class HashTask(QRunnable):
    """Worker task computing duplicate hashes in background thread pool."""

    def __init__(self, paths: list[Path], signals: TaskSignals) -> None:
        super().__init__()
        self.paths = paths
        self.signals = signals
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        results: dict[str, list[Path]] = defaultdict(list)
        for i, path in enumerate(self.paths):
            if self._cancelled:
                self.signals.cancelled.emit()
                return
            results[hash_file(path)].append(path)
            if i % 200 == 0:
                self.signals.progress.emit(i, len(self.paths))
        self.signals.finished.emit(dict(results))
