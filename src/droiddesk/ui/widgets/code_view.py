"""Read-only monospace viewer with line number gutter and target line highlighting
used for finding code context, manifest XML, and log excerpts.
"""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget


class LineNumberArea(QWidget):
    def __init__(self, editor: CodeView) -> None:
        super().__init__(editor)
        self.editor = editor

    @override
    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        self.editor.line_number_area_paint_event(event)


class CodeView(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        font = QFont("Cascadia Mono, Consolas, Courier New")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.setFont(font)

        self._highlighted_line: int | None = None
        self._line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)

        self._update_line_number_area_width(0)

        self.setStyleSheet(
            "QPlainTextEdit {"
            "    background-color: #141518;"
            "    border: 1px solid #282a30;"
            "    border-radius: 6px;"
            "    color: #e5e7eb;"
            "}"
        )

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 24 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self, _: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )

        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event: QPaintEvent) -> None:
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#101114"))

        # Right gutter divider line
        painter.setPen(QColor("#23252a"))
        painter.drawLine(
            event.rect().right(),
            event.rect().top(),
            event.rect().right(),
            event.rect().bottom(),
        )

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line_num = block_number + 1
                is_target = line_num == self._highlighted_line
                block_h = round(self.blockBoundingRect(block).height())

                if is_target:
                    # Gutter line highlight
                    painter.fillRect(
                        0,
                        top,
                        self._line_number_area.width() - 1,
                        block_h,
                        QColor("#3d1418"),
                    )
                    # Accent alert bar on left edge
                    painter.fillRect(0, top, 4, block_h, QColor("#ef4444"))
                    painter.setPen(QColor("#f87171"))
                    font = painter.font()
                    font.setBold(True)
                    painter.setFont(font)
                else:
                    painter.setPen(QColor("#4b5563"))
                    font = painter.font()
                    font.setBold(False)
                    painter.setFont(font)

                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    str(line_num),
                )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_line(self, line_number: int | None, token: str | None = None) -> None:
        self._highlighted_line = line_number
        self._line_number_area.update()

        if line_number is None or line_number < 1:
            self.setExtraSelections([])
            return

        extra_selections: list[QTextEdit.ExtraSelection] = []

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(
            QTextCursor.MoveOperation.Down,
            QTextCursor.MoveMode.MoveAnchor,
            line_number - 1,
        )

        # Visual line selection
        line_selection = QTextEdit.ExtraSelection()
        line_selection.format.setBackground(QColor("#3d1418"))
        line_selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        line_selection.cursor = cursor
        extra_selections.append(line_selection)

        # Block text background covering wrapped characters
        block_cursor = QTextCursor(cursor)
        block_cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        block_cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
        block_selection = QTextEdit.ExtraSelection()
        block_selection.format.setBackground(QColor("#3d1418"))
        block_selection.cursor = block_cursor
        extra_selections.append(block_selection)

        # Token match highlight within the line
        block = cursor.block()
        line_text = block.text()
        if token and token in line_text:
            idx = line_text.find(token)
            token_cursor = self.textCursor()
            token_cursor.setPosition(block.position() + idx)
            token_cursor.movePosition(
                QTextCursor.MoveOperation.Right,
                QTextCursor.MoveMode.KeepAnchor,
                len(token),
            )
            token_selection = QTextEdit.ExtraSelection()
            token_selection.format.setBackground(QColor("#881337"))
            token_selection.format.setForeground(QColor("#fecdd3"))
            token_selection.format.setFontWeight(QFont.Weight.Bold)
            token_selection.cursor = token_cursor
            extra_selections.append(token_selection)

        self.setExtraSelections(extra_selections)
        self.setTextCursor(cursor)
        self.centerCursor()

    def set_text(
        self,
        text: str,
        highlight_line: int | None = None,
        token: str | None = None,
    ) -> None:
        self.setPlainText(text)
        self.highlight_line(highlight_line, token)
