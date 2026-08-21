"""Security page — Section 6.5/6.6. Severity summary chips, a findings table,
and a detail panel with the recommended action and the suppression entry
point. Populated from `static_data.SECURITY_FINDINGS`; Phase 4 swaps in
`FindingsModel` bound to `ScanService` results without changing this layout.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.core.severity import Severity
from droiddesk.ui import static_data
from droiddesk.ui.static_data import FindingDisplay
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.severity_badge import SeverityBadge

_SEVERITY_TEXT_COLOR = {
    Severity.CRITICAL: "#e0574a",
    Severity.HIGH: "#e67e22",
    Severity.NEEDS_REVIEW: "#f1c40f",
    Severity.INFORMATIONAL: "#8b8e94",
}


class SecurityPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader("Secret scanner", "Detects accidental exposure, not deliberate concealment. A clean result means nothing was found by the checks performed.")
        header.add_action(QPushButton("⊘  Scan an APK"))
        scan_button = QPushButton("Scan project")
        scan_button.setProperty("role", "primary")
        header.add_action(scan_button)
        outer.addWidget(header)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)
        for label, severity, count in static_data.SECURITY_SUMMARY:
            summary_row.addWidget(self._summary_chip(label, severity, count))
        summary_row.addStretch(1)
        suppressed = QCheckBox("Show suppressed")
        summary_row.addWidget(suppressed)
        outer.addLayout(summary_row)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)

        self._table = self._build_table()
        content_row.addWidget(self._table, 2)

        self._detail = self._build_detail(static_data.SECURITY_SELECTED)
        self._detail.setFixedWidth(340)
        content_row.addWidget(self._detail)

        outer.addLayout(content_row, 1)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        default_row = static_data.SECURITY_FINDINGS.index(static_data.SECURITY_SELECTED)
        self._table.selectRow(default_row)

    def _summary_chip(self, label: str, severity: Severity, count: int) -> QWidget:
        chip = QFrame()
        chip.setProperty("role", "card")
        layout = QHBoxLayout(chip)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)
        color = _SEVERITY_TEXT_COLOR[severity]
        count_label = QLabel(str(count))
        count_label.setStyleSheet(f"color: {color}; font-weight: 800; font-size: 15px;")
        text_label = QLabel(label)
        text_label.setProperty("role", "muted")
        layout.addWidget(count_label)
        layout.addWidget(text_label)
        return chip

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(len(static_data.SECURITY_FINDINGS), 3)
        table.setHorizontalHeaderLabels(["Finding", "Location", "Preview"])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(0, 260)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        for row, item in enumerate(static_data.SECURITY_FINDINGS):
            finding = item.finding
            title_item = QTableWidgetItem(item.title)
            title_item.setForeground(Qt.GlobalColor.white if finding.severity != Severity.INFORMATIONAL else Qt.GlobalColor.gray)
            title_item.setData(Qt.ItemDataRole.UserRole, item)
            table.setItem(row, 0, title_item)

            location = f"{finding.file_path.as_posix()}:{finding.line_number}" if finding.line_number else finding.file_path.as_posix()
            location_item = QTableWidgetItem(location)
            location_item.setForeground(Qt.GlobalColor.cyan)
            table.setItem(row, 1, location_item)

            table.setItem(row, 2, QTableWidgetItem(finding.redacted))

        return table

    def _build_detail(self, item: FindingDisplay) -> QWidget:
        finding = item.finding
        card = Card()
        layout = card.body_layout()

        top_row = QHBoxLayout()
        top_row.addWidget(SeverityBadge(finding.severity))
        top_row.addStretch(1)
        rule_id = QLabel(finding.rule_id)
        rule_id.setProperty("role", "muted")
        top_row.addWidget(rule_id)
        layout.addLayout(top_row)

        title = QLabel(item.title)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 4px;")
        layout.addWidget(title)

        layout.addWidget(self._section_label("LOCATION"))
        location = f"{finding.file_path.as_posix()}:{finding.line_number}" if finding.line_number else finding.file_path.as_posix()
        location_label = QLabel(location)
        location_label.setProperty("role", "mono")
        location_label.setWordWrap(True)
        layout.addWidget(location_label)

        layout.addWidget(self._section_label("MATCHED CONTENT"))
        content_box = QFrame()
        content_box.setStyleSheet("background: #1a1b1e; border: 1px solid #2c2d33; border-radius: 6px;")
        content_layout = QVBoxLayout(content_box)
        matched = QLabel(finding.redacted)
        matched.setProperty("role", "mono")
        matched.setWordWrap(True)
        content_layout.addWidget(matched)
        layout.addWidget(content_box)

        note = QLabel("Stored redacted. DroidDesk never writes a discovered credential to its database.")
        note.setWordWrap(True)
        note.setProperty("role", "dim")
        layout.addWidget(note)

        layout.addWidget(self._section_label("RECOMMENDED ACTION"))
        action = QLabel(item.recommended_action)
        action.setWordWrap(True)
        layout.addWidget(action)

        layout.addStretch(1)

        bottom_row = QHBoxLayout()
        open_file = QPushButton("▤  Open file")
        open_file.setProperty("role", "link")
        bottom_row.addWidget(open_file)
        bottom_row.addStretch(1)
        bottom_row.addWidget(QPushButton("Suppress with a reason"))
        layout.addLayout(bottom_row)

        return card

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color: #5c5f66; font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-top: 8px;")
        return label

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        item = self._table.item(rows[0].row(), 0)
        finding_display = item.data(Qt.ItemDataRole.UserRole)
        new_detail = self._build_detail(finding_display)
        content_row = self.layout().itemAt(2).layout()
        old = content_row.itemAt(1).widget()
        content_row.replaceWidget(old, new_detail)
        old.setParent(None)
        old.deleteLater()
        new_detail.setFixedWidth(340)
        self._detail = new_detail

        # TODO(Phase 4): QTableView bound to FindingsModel, grouped/filterable
        # by severity, with Suppress writing to .droiddesk/suppressions.toml.
