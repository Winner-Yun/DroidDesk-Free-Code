"""Recordings Page: Gallery, preview, and management interface for device screen recordings."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import override

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QGuiApplication,
    QIcon,
    QPixmap,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.ui.dialogs.video_dialog import VideoRecordingDialog
from droiddesk.ui.theme import (
    ACCENT_RED,
    TEXT_MUTED,
    get_icon,
)
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.video_preview import (
    VideoPreviewWidget,
    VideoThumbnailProvider,
)


def _reveal_file(path: Path) -> None:
    """Reveal file in OS File Explorer, highlighting it if possible."""
    folder = path.parent.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        try:
            if path.exists():
                subprocess.Popen(f'explorer.exe /select,"{path}"')
                return
            subprocess.Popen(f'explorer.exe "{folder}"')
            return
        except Exception:
            pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


class RecordingsPage(QWidget):
    """Dedicated page to browse, inspect, play, and manage screen recordings."""

    navigate_requested = Signal(str)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._folder = (Path.home() / "Videos" / "DroidDesk").resolve()
        self._recordings: list[Path] = []
        self._selected_path: Path | None = None

        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # Header - strictly NO record button here per user request
        header = PageHeader(
            "Recordings",
            "Browse, inspect, play, and manage Android screen recordings.",
        )

        self._open_folder_btn = QPushButton("Open Folder")
        self._open_folder_btn.setIcon(get_icon("folder", size=13, color=TEXT_MUTED))
        self._open_folder_btn.setIconSize(QSize(13, 13))
        self._open_folder_btn.clicked.connect(self._on_open_folder_clicked)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setIcon(get_icon("rotate-cw", size=13, color=TEXT_MUTED))
        self._refresh_btn.setIconSize(QSize(13, 13))
        self._refresh_btn.clicked.connect(self._refresh_gallery)

        header.add_action(self._open_folder_btn)
        header.add_action(self._refresh_btn)
        outer.addWidget(header)

        # Main Content Container (Splitter or Empty State)
        self._content_stack = QWidget()
        self._content_layout = QVBoxLayout(self._content_stack)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)

        # Left Column: Table of recordings
        left_card = Card("SAVED RECORDINGS")
        left_layout = left_card.body_layout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filter recordings...")
        self._search_input.textChanged.connect(self._filter_table)
        left_layout.addWidget(self._search_input)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(("Filename", "Date", "Size"))
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.doubleClicked.connect(self._on_table_double_clicked)
        left_layout.addWidget(self._table, 1)

        left_card.setMinimumWidth(360)
        self._splitter.addWidget(left_card)

        # Connect thumbnail provider
        self._provider = VideoThumbnailProvider.instance()
        self._provider.thumbnail_ready.connect(self._on_provider_thumbnail_ready)

        # Right Column: Preview & Management Actions
        self._right_card = Card("PREVIEW & ACTIONS")
        right_layout = self._right_card.body_layout()

        # Video thumbnail interactive preview
        self._preview = VideoPreviewWidget(self)
        self._preview.play_requested.connect(self._on_play_clicked)
        right_layout.addWidget(self._preview, 1)

        self._title_lbl = QLabel("No recording selected")
        self._title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        right_layout.addWidget(self._title_lbl)

        self._meta_lbl = QLabel("Select a recording from the table to preview details.")
        self._meta_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; font-weight: 500;")
        right_layout.addWidget(self._meta_lbl)

        # Path display card
        path_card = QFrame()
        path_card.setProperty("role", "card")
        path_row = QHBoxLayout(path_card)
        path_row.setContentsMargins(10, 8, 10, 8)
        path_row.setSpacing(8)

        path_tag = QLabel("Path:")
        path_tag.setProperty("role", "dim")
        path_tag.setStyleSheet("font-size: 11px; font-weight: 700;")
        path_row.addWidget(path_tag)

        self._path_input = QLineEdit()
        self._path_input.setReadOnly(True)
        path_row.addWidget(self._path_input, 1)

        self._copy_path_btn = QPushButton("Copy Path")
        self._copy_path_btn.setIcon(get_icon("copy", size=13))
        self._copy_path_btn.setIconSize(QSize(13, 13))
        self._copy_path_btn.clicked.connect(self._on_copy_path_clicked)
        path_row.addWidget(self._copy_path_btn)

        right_layout.addWidget(path_card)

        # Actions Row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        self._play_btn = QPushButton("Play Video")
        self._play_btn.setProperty("role", "primary")
        self._play_btn.setIcon(get_icon("play", size=14, color="#ffffff"))
        self._play_btn.setIconSize(QSize(14, 14))
        self._play_btn.setToolTip("Open video in default media player")
        self._play_btn.clicked.connect(self._on_play_clicked)
        actions_row.addWidget(self._play_btn)

        self._view_dialog_btn = QPushButton("Open in Window")
        self._view_dialog_btn.setIcon(get_icon("maximize-2", size=13))
        self._view_dialog_btn.setIconSize(QSize(13, 13))
        self._view_dialog_btn.setToolTip("Open dedicated recording dialog")
        self._view_dialog_btn.clicked.connect(self._on_open_dialog_clicked)
        actions_row.addWidget(self._view_dialog_btn)

        self._reveal_btn = QPushButton("Show in Folder")
        self._reveal_btn.setIcon(get_icon("folder", size=13))
        self._reveal_btn.setIconSize(QSize(13, 13))
        self._reveal_btn.setToolTip("Locate video file in Windows File Explorer")
        self._reveal_btn.clicked.connect(self._on_show_in_folder_clicked)
        actions_row.addWidget(self._reveal_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setProperty("role", "danger")
        self._delete_btn.setIcon(get_icon("trash-2", size=13, color=ACCENT_RED))
        self._delete_btn.setIconSize(QSize(13, 13))
        self._delete_btn.setToolTip("Delete this video recording")
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        actions_row.addWidget(self._delete_btn)

        actions_row.addStretch(1)
        right_layout.addLayout(actions_row)

        self._splitter.addWidget(self._right_card)
        self._splitter.setStretchFactor(0, 4)
        self._splitter.setStretchFactor(1, 6)
        self._content_layout.addWidget(self._splitter)

        # Empty State
        self._empty_state = EmptyStateWidget(
            title="No Screen Recordings Yet",
            message=(
                "Screen recordings captured from the Screen Mirror page will appear here.\n"
                "Videos are automatically encoded and saved to Videos/DroidDesk."
            ),
            button_text="Go to Screen Mirror",
            icon="video",
        )
        self._empty_state.upload_requested.connect(
            lambda: self.navigate_requested.emit("screen")
        )
        self._empty_state.setVisible(False)
        self._content_layout.addWidget(self._empty_state)

        outer.addWidget(self._content_stack, 1)

        # Connect service signal if active
        if self._ctx.screen_service:
            self._ctx.screen_service.recording_saved.connect(
                lambda s, p: self._refresh_gallery()
            )

        self._refresh_gallery()

    @override
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_gallery()

    def _refresh_gallery(self) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        items = [
            p
            for p in self._folder.iterdir()
            if p.is_file() and p.suffix.lower() in (".mp4", ".mkv")
        ]
        items.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        self._recordings = items

        if not items:
            self._splitter.setVisible(False)
            self._empty_state.setVisible(True)
            self._selected_path = None
            return

        self._empty_state.setVisible(False)
        self._splitter.setVisible(True)
        self._populate_table(self._recordings)

    def _populate_table(self, items: list[Path]) -> None:
        self._table.setRowCount(len(items))
        for row, path in enumerate(items):
            name_item = QTableWidgetItem(path.name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            thumb = self._provider.get_thumbnail(path)
            if thumb and not thumb.isNull():
                scaled_icon = thumb.scaled(
                    32,
                    32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                name_item.setIcon(QIcon(scaled_icon))
            self._table.setItem(row, 0, name_item)

            try:
                mtime = path.stat().st_mtime
                dt_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                dt_str = "Unknown"
            date_item = QTableWidgetItem(dt_str)
            self._table.setItem(row, 1, date_item)

            size_str = self._format_size(path)
            size_item = QTableWidgetItem(size_str)
            self._table.setItem(row, 2, size_item)

        # Select first row if nothing selected or previous selection missing
        if self._selected_path and self._selected_path in items:
            for row in range(len(items)):
                item = self._table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == self._selected_path:
                    self._table.selectRow(row)
                    break
        elif items:
            self._table.selectRow(0)

    def _on_provider_thumbnail_ready(self, path: Path, pixmap: QPixmap) -> None:
        scaled_icon = pixmap.scaled(
            32,
            32,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                item.setIcon(QIcon(scaled_icon))
                break
        if self._selected_path and path == self._selected_path:
            self._preview.set_pixmap(pixmap)

    def _filter_table(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if not item:
                continue
            show = not needle or needle in item.text().lower()
            self._table.setRowHidden(row, not show)

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._selected_path = None
            self._update_preview()
            return
        row = rows[0].row()
        item = self._table.item(row, 0)
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(path, Path):
                self._selected_path = path
                self._update_preview()

    def _update_preview(self) -> None:
        has_sel = self._selected_path is not None and self._selected_path.exists()
        self._play_btn.setEnabled(has_sel)
        self._view_dialog_btn.setEnabled(has_sel)
        self._reveal_btn.setEnabled(has_sel)
        self._delete_btn.setEnabled(has_sel)
        self._copy_path_btn.setEnabled(has_sel)

        if not has_sel or not self._selected_path:
            self._preview.set_video_path(None)
            self._title_lbl.setText("No recording selected")
            self._meta_lbl.setText("Select a recording from the table to preview details.")
            self._path_input.setText("")
            return

        self._preview.set_video_path(self._selected_path)
        self._title_lbl.setText(self._selected_path.name)
        size_str = self._format_size(self._selected_path)
        try:
            mtime = self._selected_path.stat().st_mtime
            dt_str = datetime.fromtimestamp(mtime).strftime("%b %d, %Y  %H:%M:%S")
        except OSError:
            dt_str = "Unknown"

        self._meta_lbl.setText(f"{size_str}  •  MP4 Video (H.264)  •  {dt_str}")
        self._path_input.setText(str(self._selected_path))

    def _format_size(self, path: Path) -> str:
        try:
            size_bytes = path.stat().st_size
            if size_bytes >= 1024 * 1024:
                return f"{size_bytes / (1024 * 1024):.2f} MB"
            if size_bytes >= 1024:
                return f"{size_bytes / 1024:.1f} KB"
            return f"{size_bytes} B"
        except OSError:
            return "Unknown"

    def _on_table_double_clicked(self) -> None:
        self._on_play_clicked()

    def _on_play_clicked(self) -> None:
        if self._selected_path and self._selected_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._selected_path)))

    def _on_open_dialog_clicked(self) -> None:
        if self._selected_path and self._selected_path.exists():
            dialog = VideoRecordingDialog(self._selected_path, parent=self)
            dialog.exec()

    def _on_copy_path_clicked(self) -> None:
        if not self._selected_path:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(str(self._selected_path))
            self._copy_path_btn.setText("Copied!")
            QTimer.singleShot(1500, lambda: self._copy_path_btn.setText("Copy Path"))

    def _on_show_in_folder_clicked(self) -> None:
        if self._selected_path:
            _reveal_file(self._selected_path)

    def _on_open_folder_clicked(self) -> None:
        _reveal_file(self._folder)

    def _on_delete_clicked(self) -> None:
        if not self._selected_path or not self._selected_path.exists():
            return

        reply = QMessageBox.question(
            self,
            "Delete Recording",
            f"Are you sure you want to permanently delete:\n\n{self._selected_path.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._selected_path.unlink(missing_ok=True)
        except OSError as err:
            QMessageBox.warning(self, "Delete Failed", f"Could not delete file:\n{err}")
            return

        self._refresh_gallery()
