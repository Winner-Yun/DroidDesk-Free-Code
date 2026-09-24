"""Smart Organizer & Renamer page - Section 6.12.
Reads all files from ANY folder, generates smart rename suggestions across ALL file
extensions, provides inline editing, one-by-one and batch acceptance, and full 1-click undo.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.services.organizer_service import OrganizerService, PlannedMove
from droiddesk.ui.theme import TEXT_MUTED, get_icon
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.status_pill import StatusPill

logger = logging.getLogger(__name__)

_DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "resources" / "organizer_rules.toml"
)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class OrganizerPage(QWidget):
    upload_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._apk_path: Path | None = None
        self._planned_moves: list[PlannedMove] = []
        self._row_completed: dict[int, bool] = {}
        self._last_batch_id: str | None = None

        if ctx.organizer_service is not None:
            self._service = ctx.organizer_service
        else:
            self._service = OrganizerService(ctx.settings.data_dir / "journals")

        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "File organizer & renamer",
            "Read all files from any folder, suggest clean standardized filenames, "
            "and accept renames individually or in batch with crash-resilient 1-click undo.",
        )

        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText("Select any folder to organize...")
        self._path_input.setFixedWidth(220)
        self._path_input.returnPressed.connect(self._on_preview_plan)
        header.add_action(self._path_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.setIcon(get_icon("folder-open", size=13, color=TEXT_MUTED))
        browse_btn.setIconSize(QSize(13, 13))
        browse_btn.clicked.connect(self._on_browse_folder)
        header.add_action(browse_btn)

        view_folder_btn = QPushButton("View folder")
        view_folder_btn.setIcon(get_icon("external-link", size=13, color=TEXT_MUTED))
        view_folder_btn.setIconSize(QSize(13, 13))
        view_folder_btn.setToolTip("Open folder in Windows File Explorer")
        view_folder_btn.clicked.connect(self._on_view_folder)
        header.add_action(view_folder_btn)

        self._style_combo = QComboBox()
        self._style_combo.addItem("Smart Clean (Remove copies & junk)", "smart_clean")
        self._style_combo.addItem("kebab-case (clean-name.ext)", "kebab")
        self._style_combo.addItem("snake_case (clean_name.ext)", "snake")
        self._style_combo.addItem("Date Prefix (YYYY-MM-DD_name)", "date_prefix")
        self._style_combo.addItem("Title Case (Clean Name.ext)", "title")
        self._style_combo.setToolTip("Rename pattern to apply to filenames")
        self._style_combo.currentIndexChanged.connect(self._on_preview_plan)
        header.add_action(self._style_combo)

        preview_btn = QPushButton("Suggest renames")
        preview_btn.setIcon(get_icon("eye", size=13, color=TEXT_MUTED))
        preview_btn.setIconSize(QSize(13, 13))
        preview_btn.clicked.connect(self._on_preview_plan)
        header.add_action(preview_btn)

        self._apply_button = QPushButton("Accept all (0)")
        self._apply_button.setProperty("role", "primary")
        self._apply_button.setIcon(get_icon("check", size=13, color="#ffffff"))
        self._apply_button.setIconSize(QSize(13, 13))
        self._apply_button.setEnabled(False)
        self._apply_button.clicked.connect(self._on_apply_all_moves)
        header.add_action(self._apply_button)
        outer.addWidget(header)

        # Options row
        opt_row = QHBoxLayout()
        self._subfolders_check = QCheckBox(
            "Also organize into category subfolders (APKs/, Images/, Documents/, etc.)"
        )
        self._subfolders_check.setChecked(False)
        self._subfolders_check.stateChanged.connect(self._on_preview_plan)
        opt_row.addWidget(self._subfolders_check)
        opt_row.addStretch(1)
        outer.addLayout(opt_row)

        self._empty_banner = EmptyStateWidget(
            title="Select Any Folder to Organize & Rename",
            message=(
                "DroidDesk reads all files from any selected folder across all extensions, "
                "suggests clean standardized filenames, and allows you to accept renames "
                "individually or in batch."
            ),
            button_text="Browse Folder",
            compact=True,
        )
        self._empty_banner.upload_requested.connect(self._on_browse_folder)
        outer.addWidget(self._empty_banner)

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

        batches = self._service.recover_incomplete_batches()
        if batches:
            self._last_batch_id = batches[-1]
            self._undo_batch_label.setText(f"batch {self._last_batch_id[:8]}...")
            self._undo_btn.setEnabled(True)

        self.set_apk(None)

    def set_apk(self, path: Path | None) -> None:
        self._apk_path = path


    def _build_moves_panel(self) -> QWidget:
        card = Card("Suggested renames & preview")
        note_row = QHBoxLayout()
        note = QLabel(
            "Double-click any suggested name to edit it. Click 'Accept' to rename a file "
            "individually, or 'Accept all' to apply all suggestions at once."
        )
        note.setProperty("role", "muted")
        note_row.addWidget(note, 1)

        card_view_btn = QPushButton("Open folder")
        card_view_btn.setIcon(get_icon("external-link", size=12, color=TEXT_MUTED))
        card_view_btn.setIconSize(QSize(12, 12))
        card_view_btn.setStyleSheet("padding: 3px 8px; font-size: 11px;")
        card_view_btn.setToolTip("Open folder in Windows File Explorer")
        card_view_btn.clicked.connect(self._on_view_folder)
        note_row.addWidget(card_view_btn)

        card.body_layout().addLayout(note_row)

        self._moves_table = QTableWidget(0, 4)
        self._moves_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._moves_table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._moves_table.setHorizontalHeaderLabels(
            ["Original File", "Suggested Rename (Editable)", "What Changed", "Action"]
        )
        self._moves_table.verticalHeader().setVisible(False)
        self._moves_table.setShowGrid(False)
        self._moves_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._moves_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._moves_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._moves_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )

        card.body_layout().addWidget(self._moves_table, 1)
        return card

    def _build_duplicates_panel(self) -> QWidget:
        card = Card("Duplicates")
        note = QLabel(
            "Three-tier deduplication: file size filter, 8 KB edge hash, "
            "then full xxhash64 for guaranteed uniqueness."
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        card.body_layout().addWidget(note)

        self._dup_stat_labels: dict[str, QLabel] = {}
        stat_keys = [
            "Files examined",
            "Duplicate sets",
            "Redundant copies",
            "Recoverable space",
        ]
        for key in stat_keys:
            row = QHBoxLayout()
            k_label = QLabel(key)
            k_label.setProperty("role", "muted")
            v_label = QLabel("-")
            v_label.setStyleSheet("font-weight: 600;")
            row.addWidget(k_label, 1)
            row.addWidget(v_label)
            card.body_layout().addLayout(row)
            self._dup_stat_labels[key] = v_label

        return card

    def _build_undo_panel(self) -> QWidget:
        card = Card("Undo journal")
        self._undo_batch_label = QLabel("No active batch")
        self._undo_batch_label.setProperty("role", "mono")
        card.body_layout().addWidget(self._undo_batch_label)

        note = QLabel(
            "Written before any file operation begins and updated as each completes. "
            "If interrupted, rollback restores original names."
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        card.body_layout().addWidget(note)

        self._undo_btn = QPushButton("Undo last batch")
        self._undo_btn.setIcon(get_icon("undo", size=13, color=TEXT_MUTED))
        self._undo_btn.setIconSize(QSize(13, 13))
        self._undo_btn.setEnabled(False)
        self._undo_btn.clicked.connect(self._on_undo_batch)
        card.body_layout().addWidget(self._undo_btn)
        return card

    def _on_view_folder(self) -> None:
        """Open the currently selected folder in Windows File Explorer."""
        path_str = self._path_input.text().strip()
        if not path_str:
            QMessageBox.information(
                self, "No Folder Selected", "Please select or browse a folder first."
            )
            return

        folder = Path(path_str)
        if not folder.is_dir():
            QMessageBox.warning(
                self, "Folder Not Found", f"The directory does not exist:\n{folder}"
            )
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    def _on_table_context_menu(self, pos: QPoint) -> None:
        """Show context menu on table rows to reveal file in explorer."""
        item = self._moves_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        if row >= len(self._planned_moves):
            return

        move = self._planned_moves[row]
        menu = QMenu(self)
        reveal_action = menu.addAction(
            get_icon("external-link", size=13), "Reveal in File Explorer"
        )
        action = menu.exec(self._moves_table.viewport().mapToGlobal(pos))
        if action == reveal_action:
            self._reveal_file_in_explorer(move.source)

    def _reveal_file_in_explorer(self, file_path: Path) -> None:
        """Reveal a specific file in Windows Explorer or open its parent folder."""
        if os.name == "nt":
            try:
                subprocess.Popen(["explorer.exe", f"/select,{file_path.resolve()}"])
                return
            except Exception:
                pass
        parent = file_path.parent
        if parent.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(parent.resolve())))

    def _on_browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Organize & Rename")
        if folder:
            self._path_input.setText(folder)
            self._empty_banner.hide()
            self._on_preview_plan()

    def _on_preview_plan(self, *_: object) -> None:
        path_str = self._path_input.text().strip()
        if not path_str:
            return

        folder = Path(path_str)
        if not folder.is_dir():
            QMessageBox.warning(self, "Invalid Path", f"The directory does not exist:\n{folder}")
            return

        self._empty_banner.hide()
        style = str(self._style_combo.currentData() or "smart_clean")
        organize_subfolders = self._subfolders_check.isChecked()

        rules = None
        if organize_subfolders and _DEFAULT_RULES_PATH.is_file():
            try:
                rules = self._service.load_rules(_DEFAULT_RULES_PATH)
            except Exception as exc:
                logger.warning("Could not load rules TOML: %s", exc)

        try:
            self._planned_moves = self._service.plan(
                folder,
                rules=rules,
                style=style,
                organize_into_folders=organize_subfolders,
            )
        except Exception as exc:
            logger.error("Failed to plan renames: %s", exc)
            QMessageBox.critical(self, "Planning Error", f"Could not generate plan: {exc}")
            return

        self._row_completed.clear()
        self._populate_table()
        self._update_duplicate_stats(folder)

    def _populate_table(self) -> None:
        self._moves_table.clearContents()
        self._moves_table.clearSpans()
        if not self._planned_moves:
            self._moves_table.setRowCount(1)
            item = QTableWidgetItem(
                "All files in this folder are already clean. No renames needed."
            )
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setForeground(Qt.GlobalColor.gray)
            self._moves_table.setItem(0, 0, item)
            self._moves_table.setSpan(0, 0, 1, 4)
            self._apply_button.setText("Accept all (0)")
            self._apply_button.setEnabled(False)
            return

        self._moves_table.setRowCount(len(self._planned_moves))
        uncompleted_count = 0

        for row, move in enumerate(self._planned_moves):
            # Col 0: Original Name
            orig_item = QTableWidgetItem(move.source.name)
            orig_item.setFlags(orig_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._moves_table.setItem(row, 0, orig_item)

            # Col 1: Suggested Rename (Editable!)
            sugg_item = QTableWidgetItem(move.suggested_name)
            if move.source.name != move.suggested_name:
                sugg_item.setForeground(Qt.GlobalColor.cyan)
            self._moves_table.setItem(row, 1, sugg_item)

            # Col 2: What Changed
            reason_item = QTableWidgetItem(move.rule_name)
            reason_item.setFlags(reason_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            reason_item.setForeground(Qt.GlobalColor.gray)
            self._moves_table.setItem(row, 2, reason_item)

            # Col 3: Action (Accept button or Renamed pill)
            is_done = self._row_completed.get(row, False)
            if is_done:
                pill_widget = QWidget()
                pill_layout = QHBoxLayout(pill_widget)
                pill_layout.setContentsMargins(4, 2, 4, 2)
                pill_layout.addWidget(StatusPill("Renamed", "pass"))
                pill_layout.addStretch(1)
                self._moves_table.setCellWidget(row, 3, pill_widget)
            else:
                uncompleted_count += 1
                accept_btn = QPushButton("Accept")
                accept_btn.setIcon(get_icon("check", size=12, color="#ffffff"))
                accept_btn.setIconSize(QSize(12, 12))
                accept_btn.setProperty("role", "primary")
                accept_btn.setStyleSheet("padding: 3px 8px; font-size: 11px;")
                accept_btn.clicked.connect(lambda _=False, r=row: self._on_accept_single(r))
                self._moves_table.setCellWidget(row, 3, accept_btn)

        self._apply_button.setText(f"Accept all ({uncompleted_count})")
        self._apply_button.setEnabled(uncompleted_count > 0)

    def _on_accept_single(self, row: int) -> None:
        """Accept rename for a single file individually."""
        if row >= len(self._planned_moves) or self._row_completed.get(row, False):
            return

        move = self._planned_moves[row]

        # Read any user inline edits from the table
        edited_item = self._moves_table.item(row, 1)
        if edited_item and edited_item.text().strip():
            new_name = edited_item.text().strip()
            move = PlannedMove(
                source=move.source,
                destination=move.destination.parent / new_name,
                rule_name=move.rule_name,
                suggested_name=new_name,
                reason=move.reason,
            )
            self._planned_moves[row] = move

        try:
            batch_id = self._service.apply([move], batch_id=self._last_batch_id)
            self._last_batch_id = batch_id
            self._row_completed[row] = True

            # Update the action cell to show Renamed
            pill_widget = QWidget()
            pill_layout = QHBoxLayout(pill_widget)
            pill_layout.setContentsMargins(4, 2, 4, 2)
            pill_layout.addWidget(StatusPill("Renamed", "pass"))
            pill_layout.addStretch(1)
            self._moves_table.setCellWidget(row, 3, pill_widget)

            # Update batch undo
            self._undo_batch_label.setText(f"batch {batch_id[:8]}...")
            self._undo_btn.setEnabled(True)

            # Update remaining count on Accept all
            remaining = sum(
                1 for i in range(len(self._planned_moves)) if not self._row_completed.get(i, False)
            )
            self._apply_button.setText(f"Accept all ({remaining})")
            self._apply_button.setEnabled(remaining > 0)

        except Exception as exc:
            logger.error("Single rename failed: %s", exc)
            QMessageBox.critical(self, "Rename Failed", f"Could not rename file: {exc}")

    def _update_duplicate_stats(self, folder: Path) -> None:
        try:
            files = [p for p in folder.iterdir() if p.is_file()]
            self._dup_stat_labels["Files examined"].setText(f"{len(files):,}")

            dups = self._service.find_duplicates(files)
            dup_sets = len(dups)
            self._dup_stat_labels["Duplicate sets"].setText(str(dup_sets))

            redundant_count = sum(len(paths) - 1 for paths in dups.values())
            self._dup_stat_labels["Redundant copies"].setText(str(redundant_count))

            recoverable_bytes = 0
            for paths in dups.values():
                if len(paths) > 1:
                    try:
                        single_size = paths[0].stat().st_size
                        recoverable_bytes += single_size * (len(paths) - 1)
                    except OSError:
                        pass
            self._dup_stat_labels["Recoverable space"].setText(_format_size(recoverable_bytes))

        except Exception as exc:
            logger.warning("Duplicate analysis error: %s", exc)

    def _on_apply_all_moves(self) -> None:
        pending_moves = [
            self._planned_moves[i]
            for i in range(len(self._planned_moves))
            if not self._row_completed.get(i, False)
        ]
        if not pending_moves:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm All Renames",
            f"Are you sure you want to rename all {len(pending_moves)} remaining file(s) "
            "following the suggested names?\n\n"
            "An undo journal will be created first, allowing you to restore "
            "the original filenames at any time.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            batch_id = self._service.apply(pending_moves, batch_id=self._last_batch_id)
            self._last_batch_id = batch_id
            for i in range(len(self._planned_moves)):
                self._row_completed[i] = True

            self._undo_batch_label.setText(
                f"batch {batch_id[:8]}... · {len(self._planned_moves)} renamed"
            )
            self._undo_btn.setEnabled(True)
            self._populate_table()

            QMessageBox.information(
                self,
                "Renaming Complete",
                f"Successfully renamed {len(pending_moves)} file(s).\n"
                f"Batch ID: {batch_id}",
            )

        except Exception as exc:
            logger.error("Renaming apply failed: %s", exc)
            QMessageBox.critical(
                self,
                "Operation Interrupted",
                f"Renaming operation was interrupted: {exc}\n\n"
                "Completed operations have been saved to the journal and can be undone.",
            )

    def _on_undo_batch(self) -> None:
        batch_id = self._last_batch_id
        if not batch_id:
            batches = self._service.recover_incomplete_batches()
            if batches:
                batch_id = batches[-1]

        if not batch_id:
            QMessageBox.information(self, "No Batch", "No journal batch found to undo.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Undo",
            f"Restore original filenames for batch:\n{batch_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self._service.undo(batch_id)
            QMessageBox.information(
                self,
                "Undo Complete",
                "Original filenames have been restored successfully.",
            )
            self._undo_batch_label.setText("Batch restored")
            self._undo_btn.setEnabled(False)
            self._last_batch_id = None
            self._on_preview_plan()
        except Exception as exc:
            logger.error("Undo failed: %s", exc)
            QMessageBox.critical(self, "Undo Failed", f"Could not undo batch: {exc}")
