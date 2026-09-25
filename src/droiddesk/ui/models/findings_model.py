"""Table model displaying secret scan findings with redacted previews and severity ratings."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor

from droiddesk.core.models import Finding
from droiddesk.core.severity import Severity
from droiddesk.infra.scanner.gitleaks_mapping import rule_id_to_key_name
from droiddesk.infra.scanner.util import detect_environment_info

_COLUMNS = ("severity", "key_name", "environment", "file_path", "line_number", "redacted")
_ROOT_INDEX = QModelIndex()

_SEVERITY_COLORS = {
    Severity.CRITICAL: QColor("#e0574a"),
    Severity.HIGH: QColor("#e67e22"),
    Severity.NEEDS_REVIEW: QColor("#f1c40f"),
    Severity.INFORMATIONAL: QColor("#8b8e94"),
}


class FindingsModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._findings: list[Finding] = []

    def set_findings(self, findings: list[Finding]) -> None:
        self.beginResetModel()
        self._findings = list(findings)
        self.endResetModel()

    def findings(self) -> list[Finding]:
        return list(self._findings)

    def finding_at(self, row: int) -> Finding:
        return self._findings[row]

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._findings)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    @override
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            names = ["Severity", "Key Name", "Environment", "File", "Line", "Token / Match"]
            return names[section] if section < len(names) else _COLUMNS[section]
        return None

    @override
    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or index.row() >= len(self._findings):
            return None

        finding = self._findings[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return finding

        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return finding.severity.value.upper()
            if col == 1:
                return rule_id_to_key_name(finding.rule_id)
            if col == 2:
                tag, _ = detect_environment_info(finding.file_path, finding.rule_id)
                return tag
            if col == 3:
                if finding.file_path.name == "resources.arsc":
                    return "strings.xml"
                return finding.file_path.name
            if col == 4:
                return str(finding.line_number) if finding.line_number is not None else "-"
            if col == 5:
                return finding.redacted
            return ""

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == 1:
                return f"Rule ID: {finding.rule_id}"
            if col == 2:
                _, desc = detect_environment_info(finding.file_path, finding.rule_id)
                return desc
            if col == 3:
                if finding.file_path.name == "resources.arsc":
                    return f"{finding.file_path.parent.as_posix()}/res/values/strings.xml"
                return finding.file_path.as_posix()
            if col == 4 and finding.line_number is not None:
                return f"Line {finding.line_number}"
            if col == 5:
                return f"Matched credential: {finding.redacted}"

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 0:
                return _SEVERITY_COLORS.get(finding.severity, QColor("#8b8e94"))
            if col == 1:
                return QColor("#f3f4f6")
            if col == 2:
                return QColor("#a78bfa")
            if col == 3:
                return QColor("#5b9bd5")
            if col == 4:
                return QColor("#9ca3af")

        if role == Qt.ItemDataRole.TextAlignmentRole and col in (0, 4):
            return int(Qt.AlignmentFlag.AlignCenter)

        return None
