"""ScreenshotViewerDialog: Rich preview and management dialog for device screenshots.

Provides:
- High-fidelity image preview with smooth scaling maintaining aspect ratio.
- Image resolution, file size, and timestamp metadata.
- Full file path display with single-click "Copy Path" (clipboard text).
- "Copy Image" to clipboard (QImage) for instant pasting into Discord, Paint, Slack, docs, etc.
- "Show in Folder" to locate and select the file in Windows Explorer.
- "Delete Image" with user confirmation and gallery auto-advance.
- Gallery navigation (< Prev / Next >) to browse all screenshots in the folder.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import override

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from droiddesk.ui.theme import (
    BG_APP,
    BG_INPUT,
    BG_PANEL,
    BORDER,
    BORDER_LIGHT,
    TEXT,
    TEXT_DIM,
    TEXT_MUTED,
    get_icon,
)


class _ImagePreviewWidget(QWidget):
    """Custom widget rendering an image centered and scaled with aspect ratio preservation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(240, 240)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_APP};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap
        self.update()

    @override
    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self._pixmap and not self._pixmap.isNull():
            margin = 12
            avail_w = max(10, self.width() - (margin * 2))
            avail_h = max(10, self.height() - (margin * 2))
            scaled = self._pixmap.scaled(
                avail_w,
                avail_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No image loaded")


class ScreenshotViewerDialog(QDialog):
    """Dialog to inspect, copy, reveal, and delete a captured device screenshot."""

    def __init__(
        self,
        image_path: Path,
        device_label: str = "Android Device",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_path = Path(image_path).resolve()
        self._device_label = device_label
        self._folder = self._current_path.parent
        self._gallery: list[Path] = []
        self._current_index = 0

        self.setWindowTitle(f"Screenshot - {self._current_path.name}")
        self.resize(700, 800)
        self.setMinimumSize(540, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: #141517;
                color: {TEXT};
            }}
            QLabel {{
                color: {TEXT};
            }}
            QLineEdit {{
                background-color: {BG_INPUT};
                color: #e2e8f0;
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-family: "Cascadia Mono", Consolas, monospace;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: #3b82f6;
            }}
            QPushButton {{
                background-color: {BG_PANEL};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #2b2d33;
                border-color: {BORDER_LIGHT};
            }}
            QPushButton:pressed {{
                background-color: #222429;
            }}
            QPushButton:disabled {{
                color: {TEXT_DIM};
                border-color: #222429;
                background-color: #1a1b1e;
            }}
        """)

        self._build_ui()
        self._refresh_gallery()
        self._load_current_image()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(get_icon("camera", size=20, color="#60a5fa").pixmap(20, 20))
        header_row.addWidget(icon_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel("Device Screenshot")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        self._subtitle_lbl = QLabel(f"Device: {self._device_label}")
        self._subtitle_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        title_col.addWidget(title_lbl)
        title_col.addWidget(self._subtitle_lbl)
        header_row.addLayout(title_col)

        header_row.addStretch(1)

        close_btn = QPushButton()
        close_btn.setIcon(get_icon("x", size=14, color=TEXT_MUTED))
        close_btn.setIconSize(QSize(14, 14))
        close_btn.setFixedSize(28, 28)
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.close)
        header_row.addWidget(close_btn)
        root.addLayout(header_row)

        # Image Preview Area
        self._preview = _ImagePreviewWidget(self)
        root.addWidget(self._preview, 1)

        # Metadata Row (Resolution, Size, Date)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self._meta_lbl = QLabel("")
        self._meta_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; font-weight: 500;")
        meta_row.addWidget(self._meta_lbl)
        meta_row.addStretch(1)
        root.addLayout(meta_row)

        # Path Display & Copy Path Row
        path_card = QFrame()
        path_card.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1b1f;
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
        """)
        path_layout = QHBoxLayout(path_card)
        path_layout.setContentsMargins(10, 8, 10, 8)
        path_layout.setSpacing(8)

        path_tag = QLabel("Path:")
        path_tag.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {TEXT_MUTED};")
        path_layout.addWidget(path_tag)

        self._path_input = QLineEdit()
        self._path_input.setReadOnly(True)
        path_layout.addWidget(self._path_input, 1)

        self._copy_path_btn = QPushButton("Copy Path")
        self._copy_path_btn.setIcon(get_icon("copy", size=13, color=TEXT_MUTED))
        self._copy_path_btn.setIconSize(QSize(13, 13))
        self._copy_path_btn.setToolTip("Copy file path to clipboard")
        self._copy_path_btn.clicked.connect(self._on_copy_path_clicked)
        path_layout.addWidget(self._copy_path_btn)

        root.addWidget(path_card)

        # Bottom Actions Bar
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        # Gallery Navigation
        self._prev_btn = QPushButton()
        self._prev_btn.setIcon(get_icon("chevron-left", size=14, color=TEXT_MUTED))
        self._prev_btn.setIconSize(QSize(14, 14))
        self._prev_btn.setFixedSize(32, 32)
        self._prev_btn.setToolTip("Previous screenshot")
        self._prev_btn.clicked.connect(self._on_prev_clicked)
        actions_row.addWidget(self._prev_btn)

        self._gallery_lbl = QLabel("1 of 1")
        self._gallery_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; min-width: 50px;")
        self._gallery_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions_row.addWidget(self._gallery_lbl)

        self._next_btn = QPushButton()
        self._next_btn.setIcon(get_icon("chevron-right", size=14, color=TEXT_MUTED))
        self._next_btn.setIconSize(QSize(14, 14))
        self._next_btn.setFixedSize(32, 32)
        self._next_btn.setToolTip("Next screenshot")
        self._next_btn.clicked.connect(self._on_next_clicked)
        actions_row.addWidget(self._next_btn)

        actions_row.addStretch(1)

        # Action: Copy Image (Raw QImage to Clipboard)
        self._copy_img_btn = QPushButton("Copy Image")
        self._copy_img_btn.setIcon(get_icon("copy", size=14, color="#ffffff"))
        self._copy_img_btn.setIconSize(QSize(14, 14))
        self._copy_img_btn.setToolTip(
            "Copy image to clipboard (paste into Paint, Discord, Slack, etc.)"
        )
        self._copy_img_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #3b82f6;
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
                border-color: #60a5fa;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
        """)
        self._copy_img_btn.clicked.connect(self._on_copy_image_clicked)
        actions_row.addWidget(self._copy_img_btn)

        # Action: Show in Explorer
        self._open_folder_btn = QPushButton("Show in Folder")
        self._open_folder_btn.setIcon(get_icon("folder", size=14, color=TEXT_MUTED))
        self._open_folder_btn.setIconSize(QSize(14, 14))
        self._open_folder_btn.setToolTip("Open containing folder in Windows Explorer")
        self._open_folder_btn.clicked.connect(self._on_show_in_folder_clicked)
        actions_row.addWidget(self._open_folder_btn)

        # Action: Delete
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setIcon(get_icon("trash-2", size=14, color="#ef4444"))
        self._delete_btn.setIconSize(QSize(14, 14))
        self._delete_btn.setToolTip("Delete this screenshot from disk")
        self._delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #201315;
                color: #f87171;
                border: 1px solid #4a2226;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3b171c;
                border-color: #ef4444;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #4c1d24;
            }
        """)
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        actions_row.addWidget(self._delete_btn)

        root.addLayout(actions_row)

    def _refresh_gallery(self) -> None:
        """Find all PNG screenshots in the folder sorted newest first."""
        if not self._folder.exists():
            self._gallery = [self._current_path]
            self._current_index = 0
            return

        items = [
            p for p in self._folder.glob("*.png")
            if p.is_file()
        ]
        items.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        self._gallery = items if items else [self._current_path]

        try:
            self._current_index = self._gallery.index(self._current_path)
        except ValueError:
            self._gallery.insert(0, self._current_path)
            self._current_index = 0

    def _load_current_image(self) -> None:
        if not self._current_path.exists():
            self._preview.set_pixmap(None)
            self._meta_lbl.setText("File does not exist")
            self._path_input.setText(str(self._current_path))
            return

        pix = QPixmap(str(self._current_path))
        self._preview.set_pixmap(pix)
        self._path_input.setText(str(self._current_path))
        self.setWindowTitle(f"Screenshot - {self._current_path.name}")

        try:
            size_bytes = self._current_path.stat().st_size
            if size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.2f} MB"

            mtime = datetime.fromtimestamp(self._current_path.stat().st_mtime)
            date_str = mtime.strftime("%b %d, %Y %H:%M:%S")

            if not pix.isNull():
                res_str = f"{pix.width()} x {pix.height()} px"
            else:
                res_str = "Unknown resolution"

            self._meta_lbl.setText(f"{res_str}  •  {size_str}  •  {date_str}")
        except Exception:
            self._meta_lbl.setText("")

        total = len(self._gallery)
        idx = self._current_index
        self._gallery_lbl.setText(f"{idx + 1} of {total}")
        self._prev_btn.setEnabled(idx > 0)
        self._next_btn.setEnabled(idx < total - 1)

    def _on_prev_clicked(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._current_path = self._gallery[self._current_index]
            self._load_current_image()

    def _on_next_clicked(self) -> None:
        if self._current_index < len(self._gallery) - 1:
            self._current_index += 1
            self._current_path = self._gallery[self._current_index]
            self._load_current_image()

    def _on_copy_path_clicked(self) -> None:
        path_str = str(self._current_path)
        QGuiApplication.clipboard().setText(path_str)
        self._copy_path_btn.setText("Copied!")
        self._copy_path_btn.setIcon(get_icon("check", size=13, color="#22c55e"))
        QTimer.singleShot(1800, self._restore_copy_path_btn)

    def _restore_copy_path_btn(self) -> None:
        self._copy_path_btn.setText("Copy Path")
        self._copy_path_btn.setIcon(get_icon("copy", size=13, color=TEXT_MUTED))

    def _on_copy_image_clicked(self) -> None:
        if not self._current_path.exists():
            return
        image = QImage(str(self._current_path))
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
        if not self._current_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._folder)))
            return

        if os.name == "nt":
            try:
                subprocess.Popen(["explorer.exe", f"/select,{self._current_path}"])
                return
            except Exception:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._folder)))

    def _on_delete_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Screenshot",
            "Are you sure you want to permanently delete this screenshot?\n\n"
            f"{self._current_path.name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._current_path.unlink(missing_ok=True)
        except OSError as err:
            QMessageBox.warning(self, "Delete Failed", f"Could not delete file:\n{err}")
            return

        if self._current_path in self._gallery:
            self._gallery.remove(self._current_path)

        if not self._gallery:
            QMessageBox.information(
                self,
                "Deleted",
                "The screenshot has been deleted.\nNo other screenshots remain in this folder.",
            )
            self.accept()
            return

        if self._current_index >= len(self._gallery):
            self._current_index = len(self._gallery) - 1

        self._current_path = self._gallery[self._current_index]
        self._load_current_image()
