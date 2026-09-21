"""FilesModel — backs the Smart Organizer page (Section 6.12). Shows the planned
source/destination moves for review before Apply commits them.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt

_COLUMNS = ("source", "destination")
_ROOT_INDEX = QModelIndex()


class FilesModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._rows: list[tuple[Path, Path]] = []

    def set_planned_moves(self, moves: list[tuple[Path, Path]]) -> None:
        self.beginResetModel()
        self._rows = moves
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section].capitalize()
        return None

    def data(  # noqa: N802
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return str(self._rows[index.row()][index.column()])
