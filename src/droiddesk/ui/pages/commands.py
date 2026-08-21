"""Commands page — Section 6.9. Safe Command Runner: guard checklist on the
left, embedded output console on the right. Populated from
`static_data.BUILD_GUARDS`; Phase 5 swaps in `BuildService.guard_evaluated` /
`output_line` without changing this layout. The Release Gate verdict lives on
its own page (`ui/pages/gate.py`), matching the separate sidebar entry in the
mockups.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from droiddesk.ui import static_data
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.status_pill import StatusIcon, TagPill


class CommandsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader("Build commands", "Guards run before the command does. A failing guard either warns and lets you acknowledge it, or blocks outright.")
        command_input = QLineEdit(static_data.BUILD_COMMAND_NAME)
        command_input.setFixedWidth(220)
        header.add_action(command_input)
        run_button = QPushButton("Check guards and run")
        run_button.setProperty("role", "primary")
        header.add_action(run_button)
        outer.addWidget(header)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        columns.addWidget(self._build_guards_panel(), 1)
        columns.addWidget(self._build_output_panel(), 1)
        outer.addLayout(columns, 1)

    def _build_guards_panel(self) -> QWidget:
        card = Card("Guards")
        layout = card.body_layout()
        for guard in static_data.BUILD_GUARDS:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(StatusIcon(guard.status))

            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            name = QLabel(guard.name)
            name.setStyleSheet("font-weight: 600; font-family: 'Cascadia Mono'; font-size: 12px;")
            detail = QLabel(guard.detail)
            detail.setProperty("role", "muted")
            text_col.addWidget(name)
            text_col.addWidget(detail)
            row.addLayout(text_col, 1)

            if guard.tag:
                row.addWidget(TagPill(guard.tag))

            layout.addLayout(row)

        note = QLabel(static_data.BUILD_GUARD_NOTE)
        note.setWordWrap(True)
        note.setProperty("role", "dim")
        note.setStyleSheet(note.styleSheet() + " margin-top: 8px;")
        layout.addWidget(note)
        layout.addStretch(1)
        return card

    def _build_output_panel(self) -> QWidget:
        card = Card("Output")
        console = QPlainTextEdit()
        console.setReadOnly(True)
        console.setPlainText(static_data.BUILD_OUTPUT)
        card.body_layout().addWidget(console, 1)
        return card

    # TODO(Phase 5): guard checklist bound to BuildService.guard_evaluated,
    # embedded terminal fed by output_line, and the override dialog that
    # requires a typed reason.
