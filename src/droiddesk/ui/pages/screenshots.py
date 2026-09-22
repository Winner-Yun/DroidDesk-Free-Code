"""Screenshots Page: Gallery, preview, and management interface for device captures."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import override

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QDesktopServices,
    QGuiApplication,
    QImage,
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
from droiddesk.ui.dialogs.screenshot_dialog import (
    ScreenshotViewerDialog,
    _ImagePreviewWidget,
)
from droiddesk.ui.theme import (
    BORDER,
    TEXT_MUTED,
    get_icon,
)
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget


class ScreenshotsPage(QWidget):
    """Dedicated page to browse, view, copy, and manage screenshots."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._folder = Path.home() / "Pictures" / "DroidDesk"
        self._screenshots: list[Path] = []
        self._selected_path: Path | None = None

        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # Header
        header = PageHeader(
            "Screenshots",
            "Browse, view, copy, and manage Android screenshots captured across devices.",
        )

        self._capture_btn = QPushButton("Take Screenshot")
        self._capture_btn.setIcon(get_icon("camera", size=13, color="#ffffff"))
        self._capture_btn.setIconSize(QSize(13, 13))
        self._capture_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #3b82f6;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self._capture_btn.clicked.connect(self._on_take_screenshot_clicked)

        self._open_folder_btn = QPushButton("Open Folder")
        self._open_folder_btn.setIcon(get_icon("folder", size=13, color=TEXT_MUTED))
        self._open_folder_btn.setIconSize(QSize(13, 13))
        self._open_folder_btn.clicked.connect(self._on_open_folder_clicked)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setIcon(get_icon("rotate-cw", size=13, color=TEXT_MUTED))
        self._refresh_btn.setIconSize(QSize(13, 13))
        self._refresh_btn.clicked.connect(self._refresh_gallery)

        header.add_action(self._capture_btn)
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

        # Left Column: Table of screenshots
        left_card = Card("SAVED SCREENSHOTS")
        left_layout = left_card.body_layout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filter screenshots...")
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

        # Right Column: Preview & Management Actions
        self._right_card = Card("PREVIEW & ACTIONS")
        right_layout = self._right_card.body_layout()

        self._preview = _ImagePreviewWidget()
        right_layout.addWidget(self._preview, 1)

        # Metadata Label
        self._meta_lbl = QLabel("No screenshot selected")
        self._meta_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; font-weight: 500;")
        right_layout.addWidget(self._meta_lbl)

        # Path display card
        path_card = QFrame()
        path_card.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1b1f;
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        path_row = QHBoxLayout(path_card)
        path_row.setContentsMargins(10, 8, 10, 8)
        path_row.setSpacing(8)

        path_tag = QLabel("Path:")
        path_tag.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {TEXT_MUTED};")
        path_row.addWidget(path_tag)

        self._path_input = QLineEdit()
        self._path_input.setReadOnly(True)
        path_row.addWidget(self._path_input, 1)

        self._copy_path_btn = QPushButton("Copy Path")
        self._copy_path_btn.setIcon(get_icon("copy", size=13, color=TEXT_MUTED))
        self._copy_path_btn.setIconSize(QSize(13, 13))
        self._copy_path_btn.clicked.connect(self._on_copy_path_clicked)
        path_row.addWidget(self._copy_path_btn)

        right_layout.addWidget(path_card)

        # Actions Row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        self._copy_img_btn = QPushButton("Copy Image")
        self._copy_img_btn.setIcon(get_icon("copy", size=14, color="#ffffff"))
        self._copy_img_btn.setIconSize(QSize(14, 14))
        self._copy_img_btn.setToolTip("Copy image to clipboard to paste in any app")
        self._copy_img_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #3b82f6;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self._copy_img_btn.clicked.connect(self._on_copy_image_clicked)
        actions_row.addWidget(self._copy_img_btn)

        self._view_dialog_btn = QPushButton("Open in Window")
        self._view_dialog_btn.setIcon(get_icon("maximize-2", size=13, color=TEXT_MUTED))
        self._view_dialog_btn.setIconSize(QSize(13, 13))
        self._view_dialog_btn.setToolTip("Open full-size screenshot viewer dialog")
        self._view_dialog_btn.clicked.connect(self._on_open_dialog_clicked)
        actions_row.addWidget(self._view_dialog_btn)

        self._reveal_btn = QPushButton("Show in Folder")
        self._reveal_btn.setIcon(get_icon("folder", size=13, color=TEXT_MUTED))
        self._reveal_btn.setIconSize(QSize(13, 13))
        self._reveal_btn.setToolTip("Locate file in Windows Explorer")
        self._reveal_btn.clicked.connect(self._on_show_in_folder_clicked)
        actions_row.addWidget(self._reveal_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setIcon(get_icon("trash-2", size=13, color="#ef4444"))
        self._delete_btn.setIconSize(QSize(13, 13))
        self._delete_btn.setToolTip("Delete this screenshot")
        self._delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #201315;
                color: #f87171;
                border: 1px solid #4a2226;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3b171c;
                border-color: #ef4444;
                color: #ffffff;
            }
        """)
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
            title="No Screenshots Captured Yet",
            message="Capture screenshots from connected Android devices to view and manage them.",
            button_text="Take Screenshot",
            icon="camera",
        )
        self._empty_state.upload_requested.connect(self._on_take_screenshot_clicked)
        self._empty_state.setVisible(False)
        self._content_layout.addWidget(self._empty_state)

        outer.addWidget(self._content_stack, 1)

        self._refresh_gallery()

    @override
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_gallery()

    def _refresh_gallery(self) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        items = [p for p in self._folder.glob("*.png") if p.is_file()]
        items.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        self._screenshots = items

        if not items:
            self._splitter.setVisible(False)
            self._empty_state.setVisible(True)
            self._selected_path = None
            return

        self._empty_state.setVisible(False)
        self._splitter.setVisible(True)
        self._populate_table(self._screenshots)

    def _populate_table(self, items: list[Path]) -> None:
        self._table.setRowCount(len(items))
        for row, path in enumerate(items):
            # Filename item
            name_item = QTableWidgetItem(path.name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            self._table.setItem(row, 0, name_item)

            # Date item
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                date_str = mtime.strftime("%b %d, %H:%M")
            except Exception:
                date_str = "—"
            date_item = QTableWidgetItem(date_str)
            date_item.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, 1, date_item)

            # Size item
            try:
                sz = path.stat().st_size
                sz_str = (
                    f"{sz / 1024:.1f} KB"
                    if sz < 1024 * 1024
                    else f"{sz / (1024 * 1024):.2f} MB"
                )
            except Exception:
                sz_str = "—"
            size_item = QTableWidgetItem(sz_str)
            size_item.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, 2, size_item)

        # Restore selection
        if self._selected_path:
            for r in range(self._table.rowCount()):
                item = self._table.item(r, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == self._selected_path:
                    self._table.selectRow(r)
                    return
        if self._table.rowCount() > 0:
            self._table.selectRow(0)

    def _filter_table(self, query: str) -> None:
        q = query.strip().lower()
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item:
                matches = not q or q in item.text().lower()
                self._table.setRowHidden(r, not matches)

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        item = self._table.item(rows[0].row(), 0)
        if item is None:
            return
        path: Path = item.data(Qt.ItemDataRole.UserRole)
        self._selected_path = path
        self._display_selected_image(path)

    def _display_selected_image(self, path: Path) -> None:
        if not path.exists():
            self._preview.set_pixmap(None)
            self._meta_lbl.setText("File does not exist")
            self._path_input.setText(str(path))
            return

        pix = QPixmap(str(path))
        self._preview.set_pixmap(pix)
        self._path_input.setText(str(path))

        try:
            size_bytes = path.stat().st_size
            size_str = (
                f"{size_bytes / 1024:.1f} KB"
                if size_bytes < 1024 * 1024
                else f"{size_bytes / (1024 * 1024):.2f} MB"
            )
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            date_str = mtime.strftime("%b %d, %Y %H:%M:%S")
            res_str = (
                f"{pix.width()} x {pix.height()} px"
                if not pix.isNull()
                else "Unknown resolution"
            )
            self._meta_lbl.setText(f"{res_str}  •  {size_str}  •  {date_str}")
        except Exception:
            self._meta_lbl.setText("")

    def _on_table_double_clicked(self) -> None:
        self._on_open_dialog_clicked()

    def _on_open_dialog_clicked(self) -> None:
        if not self._selected_path or not self._selected_path.exists():
            return
        dialog = ScreenshotViewerDialog(self._selected_path, parent=self)
        dialog.exec()
        self._refresh_gallery()

    def _on_copy_path_clicked(self) -> None:
        if not self._selected_path:
            return
        QGuiApplication.clipboard().setText(str(self._selected_path))
        self._copy_path_btn.setText("Copied!")
        self._copy_path_btn.setIcon(get_icon("check", size=13, color="#22c55e"))
        QTimer.singleShot(1800, self._restore_copy_path_btn)

    def _restore_copy_path_btn(self) -> None:
        self._copy_path_btn.setText("Copy Path")
        self._copy_path_btn.setIcon(get_icon("copy", size=13, color=TEXT_MUTED))

    def _on_copy_image_clicked(self) -> None:
        if not self._selected_path or not self._selected_path.exists():
            return
        image = QImage(str(self._selected_path))
        if not image.isNull():
            cb = QGuiApplication.clipboard()
            cb.setImage(image)
            pix = QPixmap.fromImage(image)
            cb.setPixmap(pix)
            self._copy_img_btn.setText("Image Copied!")
            self._copy_img_btn.setIcon(get_icon("check", size=14, color="#ffffff"))
            QTimer.singleShot(2000, self._restore_copy_img_btn)

    def _restore_copy_img_btn(self) -> None:
        self._copy_img_btn.setText("Copy Image")
        self._copy_img_btn.setIcon(get_icon("copy", size=14, color="#ffffff"))

    def _on_show_in_folder_clicked(self) -> None:
        if not self._selected_path or not self._selected_path.exists():
            self._on_open_folder_clicked()
            return
        if os.name == "nt":
            try:
                subprocess.Popen(["explorer.exe", f"/select,{self._selected_path}"])
                return
            except Exception:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._folder)))

    def _on_open_folder_clicked(self) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._folder)))

    def _on_delete_clicked(self) -> None:
        if not self._selected_path or not self._selected_path.exists():
            return

        reply = QMessageBox.question(
            self,
            "Delete Screenshot",
            f"Are you sure you want to delete '{self._selected_path.name}'?\n\n"
            "This will permanently delete the file from disk.",
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

    def _on_take_screenshot_clicked(self) -> None:
        devices = [d for d in self._ctx.device_service.devices() if d.state == "device"]
        if not devices:
            QMessageBox.warning(
                self,
                "No Device Connected",
                "No Android device or emulator is currently connected and authorized.\n\n"
                "Please connect a device via USB/Wi-Fi or start an emulator.",
            )
            return

        device = devices[0]
        self._capture_btn.setEnabled(False)
        self._capture_btn.setText("Capturing...")
        QGuiApplication.processEvents()

        try:
            shot_path = self._ctx.device_service.take_screenshot(device.serial)
            self._selected_path = shot_path
            self._refresh_gallery()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Screenshot Failed",
                f"Failed to capture screenshot from '{device.serial}':\n\n{exc}",
            )
        finally:
            self._capture_btn.setEnabled(True)
            self._capture_btn.setText("Take Screenshot")
