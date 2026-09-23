"""LogcatModel - Section 8.4, verbatim. A logcat stream can produce thousands of
lines per second during app startup; calling beginInsertRows/endInsertRows per line
would make the interface unresponsive. Batching model signals to a fixed 100ms
interval decouples interface responsiveness from log volume entirely.

Lines are parsed into structured columns (threadtime format) rather than displayed
raw, which is what makes filtering and colouring possible (Section 6.4).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import override

import regex
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt, QTimer

_EMPTY_INDEX = QModelIndex()

# `MM-DD HH:MM:SS.mmm  PID  TID PRIORITY TAG: message`
_THREADTIME_RE = regex.compile(
    r"^(?P<timestamp>\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+"
    r"(?P<pid>\d+)\s+(?P<tid>\d+)\s+(?P<priority>[VDIWEF])\s+"
    r"(?P<tag>[^:]+):\s?(?P<message>.*)$"
)

_COLUMNS = ("timestamp", "pid", "tid", "priority", "tag", "message")
_COLUMN_HEADERS = ("Time", "PID", "TID", "Level", "Tag", "Message")


@dataclass(slots=True)
class LogLine:
    timestamp: str
    pid: int
    tid: int
    priority: str
    tag: str
    message: str
    raw: str


def parse_threadtime(raw: str) -> LogLine | None:
    match = _THREADTIME_RE.match(raw)
    if not match:
        return None
    return LogLine(
        timestamp=match["timestamp"],
        pid=int(match["pid"]),
        tid=int(match["tid"]),
        priority=match["priority"],
        tag=match["tag"].strip(),
        message=match["message"],
        raw=raw,
    )


class LogcatModel(QAbstractTableModel):
    def __init__(self, capacity: int = 50_000) -> None:
        super().__init__()
        self._rows: deque[LogLine] = deque(maxlen=capacity)
        self._pending: list[LogLine] = []
        self._paused = False
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._flush)
        self._timer.start()

    def queue(self, raw_line: str) -> None:
        if self._paused:
            return
        parsed = parse_threadtime(raw_line)
        if parsed is not None:
            self._pending.append(parsed)  # cheap; no model signal

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    def clear(self) -> None:
        self.beginResetModel()
        self._rows.clear()
        self._pending.clear()
        self.endResetModel()

    def _flush(self) -> None:
        if not self._pending:
            return
        # deque with maxlen evicts from the front automatically, so a full reset
        # is simpler and correct at this batch size
        self.beginResetModel()
        self._rows.extend(self._pending)
        self._pending.clear()
        self.endResetModel()

    # -- QAbstractTableModel ------------------------------------------------

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _EMPTY_INDEX) -> int:
        return 0 if parent.isValid() else len(self._rows)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _EMPTY_INDEX) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    @override
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMN_HEADERS[section]
        return None

    @override
    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        line = self._rows[index.row()]
        return getattr(line, _COLUMNS[index.column()])
