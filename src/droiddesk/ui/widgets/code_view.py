"""Read-only monospace viewer used for log excerpts, manifest XML, and finding
context lines.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit


class CodeView(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        font = QFont("Cascadia Mono")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

    def set_text(self, text: str, highlight_line: int | None = None) -> None:
        self.setPlainText(text)
        # TODO(Phase 2): highlight `highlight_line` when set (used by the
        # Security page to jump to a finding's matched line).
