"""FindingsModel — backs the Security page (Section 6.5/6.6). Displays redacted
previews only; the raw matched text never reaches the UI layer, matching the
"never store the secret itself" rule in Section 7.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from droiddesk.core.models import Finding

_COLUMNS = ("severity", "rule_id", "file_path", "line_number", "redacted")


class FindingsModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._findings: list[Finding] = []

    def set_findings(self, findings: list[Finding]) -> None:
        self.beginResetModel()
        self._findings = findings
        self.endResetModel()

    def finding_at(self, row: int) -> Finding:
        return self._findings[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._findings)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _COLUMNS[section].replace("_", " ").capitalize()
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        finding = self._findings[index.row()]
        value = getattr(finding, _COLUMNS[index.column()])
        return str(value) if value is not None else ""
