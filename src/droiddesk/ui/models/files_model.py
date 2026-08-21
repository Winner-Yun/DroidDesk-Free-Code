"""FilesModel — backs the Smart Organizer page (Section 6.12). Shows the planned
source/destination moves for review before Apply commits them.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

_COLUMNS = ("source", "destination")


class FilesModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._rows: list[tuple[Path, Path]] = []

    def set_planned_moves(self, moves: list[tuple[Path, Path]]) -> None:
        self.beginResetModel()
        self._rows = moves
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section].capitalize()
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return str(self._rows[index.row()][index.column()])
