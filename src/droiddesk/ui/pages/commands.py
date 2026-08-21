"""Commands page — Section 6.9/6.10. Safe Command Runner (command profiles, guard
results, embedded terminal) and the Release Gate verdict.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class CommandsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Commands & Release Gate — Phase 5"))
        # TODO(Phase 5): guard checklist bound to BuildService.guard_evaluated,
        # an embedded terminal for output_line, and the override dialog that
        # requires a typed reason.
