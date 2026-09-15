"""Smart Organizer page — Section 6.12. Path picker, hashing progress, the
planned-moves preview table, duplicate-scan stats, and the undo journal.
Populated from `static_data.ORGANIZER_PLANNED_MOVES`; Phase 6 swaps in
`OrganizerService.plan()` / `apply()` / `undo()` without changing this layout.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.ui import static_data
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget


class OrganizerPage(QWidget):
    upload_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._apk_path: Path | None = None
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "File organizer",
            "Nothing moves until you have seen the plan. Every batch writes an undo "
            "journal first, and deletions go to the Recycle Bin.",
        )
        path_input = QLineEdit(static_data.ORGANIZER_PATH)
        path_input.setFixedWidth(220)
        header.add_action(path_input)
        header.add_action(QPushButton("▽  Preview plan"))
        apply_button = QPushButton(f"Apply {len(static_data.ORGANIZER_PLANNED_MOVES)} moves")
        apply_button.setProperty("role", "primary")
        header.add_action(apply_button)
        outer.addWidget(header)

        self._empty_banner = EmptyStateWidget(
            title="No Active APK Selected",
            message=(
                "Organize, deduplicate, and sort Android packages. Upload an APK "
                "or add APK directories to analyze your files."
            ),
            button_text="Upload APK",
            compact=True,
        )
        self._empty_banner.upload_requested.connect(self.upload_requested.emit)
        outer.addWidget(self._empty_banner)

        outer.addLayout(self._build_progress_row())

        content_row = QHBoxLayout()
        content_row.setSpacing(14)
        content_row.addWidget(self._build_moves_panel(), 2)

        side_col = QVBoxLayout()
        side_col.setSpacing(14)
        side_col.addWidget(self._build_duplicates_panel())
        side_col.addWidget(self._build_undo_panel())
        side_col.addStretch(1)
        content_row.addLayout(side_col, 1)

        outer.addLayout(content_row, 1)

        self.set_apk(None)

    def set_apk(self, path: Path | None) -> None:
        self._apk_path = path
        if path is None:
            self._empty_banner.show()
        else:
            self._empty_banner.hide()

    def _build_progress_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel(static_data.ORGANIZER_HASH_PROGRESS_LABEL)
        label.setProperty("role", "muted")
        row.addWidget(label)
        bar = QProgressBar()
        current, total = static_data.ORGANIZER_HASH_PROGRESS
        bar.setRange(0, total)
        bar.setValue(current)
        row.addWidget(bar, 1)
        row.addWidget(QPushButton("☐  Cancel"))
        return row

    def _build_moves_panel(self) -> QWidget:
        card = Card("Planned moves")
        note = QLabel("First matching rule wins, by priority.")
        note.setProperty("role", "muted")
        card.body_layout().addWidget(note)

        table = QTableWidget(len(static_data.ORGANIZER_PLANNED_MOVES), 3)
        table.setHorizontalHeaderLabels(["File", "Rule", "Destination"])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for row, move in enumerate(static_data.ORGANIZER_PLANNED_MOVES):
            table.setItem(row, 0, QTableWidgetItem(move.file_name))
            table.setItem(row, 1, QTableWidgetItem(move.rule))
            dest_item = QTableWidgetItem(move.destination)
            dest_item.setForeground(Qt.GlobalColor.cyan)
            table.setItem(row, 2, dest_item)

        card.body_layout().addWidget(table, 1)
        return card

    def _build_duplicates_panel(self) -> QWidget:
        card = Card("Duplicates")
        note = QLabel(
            "Three tiers: size, then first and last 8 KB, then a full xxhash. "
            "Full reads dropped by 94% on this folder."
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        card.body_layout().addWidget(note)

        for label, value in static_data.ORGANIZER_DUPLICATE_STATS:
            row = QHBoxLayout()
            key = QLabel(label)
            key.setProperty("role", "muted")
            value_label = QLabel(value)
            value_label.setStyleSheet("font-weight: 600;")
            row.addWidget(key, 1)
            row.addWidget(value_label)
            card.body_layout().addLayout(row)
        return card

    def _build_undo_panel(self) -> QWidget:
        card = Card("Undo journal")
        batch = QLabel(static_data.ORGANIZER_UNDO_BATCH_ID)
        batch.setProperty("role", "mono")
        card.body_layout().addWidget(batch)

        note = QLabel(static_data.ORGANIZER_UNDO_NOTE)
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        card.body_layout().addWidget(note)

        card.body_layout().addWidget(QPushButton("Undo last batch"))
        return card

    # TODO(Phase 6): bind the moves table to FilesModel, wire Apply to
    # OrganizerService.apply(), and Undo last batch to OrganizerService.undo().
