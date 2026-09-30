"""VideoRecordingDialog: Modal viewer and manager for saved screen recordings."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.ui.theme import (
    ACCENT_GREEN,
    BG_INPUT,
    BG_PANEL,
    BORDER,
    BORDER_LIGHT,
    TEXT,
    TEXT_DIM,
    TEXT_MUTED,
    get_icon,
)
from droiddesk.ui.widgets.video_preview import VideoPreviewWidget


class VideoRecordingDialog(QDialog):
    """Rich dialog presented when an Android screen recording completes."""

    def __init__(
        self,
        video_path: Path,
        device_label: str = "Android Device",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._video_path = Path(video_path).resolve()
        self._device_label = device_label

        self.setWindowTitle("Screen Recording Saved")
        self.resize(540, 560)
        self.setMinimumSize(480, 480)
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
                padding: 7px 14px;
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

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(16)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_box = QFrame()
        icon_box.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(52, 211, 153, 0.12);
                border: 1px solid {ACCENT_GREEN};
                border-radius: 8px;
            }}
        """)
        icon_box.setFixedSize(40, 40)
        ib_layout = QVBoxLayout(icon_box)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("video", size=20, color=ACCENT_GREEN).pixmap(20, 20))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ib_layout.addWidget(icon_lbl)
        header_row.addWidget(icon_box)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel("Screen Recording Ready")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        sub_lbl = QLabel(f"Device: {self._device_label}")
        sub_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        header_row.addLayout(title_col)

        header_row.addStretch(1)

        close_btn = QPushButton()
        close_btn.setIcon(get_icon("x", size=13, color=TEXT_MUTED))
        close_btn.setIconSize(QSize(13, 13))
        close_btn.setFixedSize(28, 28)
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.close)
        header_row.addWidget(close_btn)
        root.addLayout(header_row)

        # Video Frame Thumbnail Preview
        self._preview = VideoPreviewWidget(self)
        self._preview.set_video_path(self._video_path)
        self._preview.play_requested.connect(self._on_play_video)
        root.addWidget(self._preview, 1)

        # Video Information Card
        info_card = QFrame()
        info_card.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1b1f;
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        info_layout = QVBoxLayout(info_card)
        info_layout.setSpacing(8)

        file_row = QHBoxLayout()
        file_lbl = QLabel("File Name:")
        file_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {TEXT_MUTED}; min-width: 75px;"
        )
        file_val = QLabel(self._video_path.name)
        file_val.setStyleSheet("font-size: 12px; font-weight: 600; color: #60a5fa;")
        file_row.addWidget(file_lbl)
        file_row.addWidget(file_val, 1)
        info_layout.addLayout(file_row)

        # File Size & Format Row
        size_str = self._format_file_size()
        meta_row = QHBoxLayout()
        meta_lbl = QLabel("Size & Format:")
        meta_lbl.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {TEXT_MUTED}; min-width: 75px;"
        )
        meta_val = QLabel(f"{size_str}  •  MP4 Video (H.264)")
        meta_val.setStyleSheet(f"font-size: 12px; color: {TEXT};")
        meta_row.addWidget(meta_lbl)
        meta_row.addWidget(meta_val, 1)
        info_layout.addLayout(meta_row)

        root.addWidget(info_card)

        # Path Row with Copy Button
        path_card = QFrame()
        path_card.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1b1f;
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        path_layout = QHBoxLayout(path_card)
        path_layout.setContentsMargins(10, 8, 10, 8)
        path_layout.setSpacing(8)

        path_tag = QLabel("Path:")
        path_tag.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {TEXT_MUTED};")
        path_layout.addWidget(path_tag)

        self._path_input = QLineEdit(str(self._video_path))
        self._path_input.setReadOnly(True)
        path_layout.addWidget(self._path_input, 1)

        self._copy_btn = QPushButton("Copy Path")
        self._copy_btn.setIcon(get_icon("copy", size=13, color=TEXT_MUTED))
        self._copy_btn.setIconSize(QSize(13, 13))
        self._copy_btn.clicked.connect(self._on_copy_path)
        path_layout.addWidget(self._copy_btn)

        root.addWidget(path_card)
        root.addStretch(1)

        # Action Buttons
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        open_folder_btn = QPushButton("Open Folder")
        open_folder_btn.setIcon(get_icon("folder", size=13, color=TEXT_MUTED))
        open_folder_btn.setIconSize(QSize(13, 13))
        open_folder_btn.clicked.connect(self._on_open_folder)
        actions_row.addWidget(open_folder_btn)

        actions_row.addStretch(1)

        cancel_btn = QPushButton("Close")
        cancel_btn.clicked.connect(self.close)
        actions_row.addWidget(cancel_btn)

        play_btn = QPushButton("Play Video")
        play_btn.setProperty("role", "primary")
        play_btn.setIcon(get_icon("play", size=13, color="#ffffff"))
        play_btn.setIconSize(QSize(13, 13))
        play_btn.clicked.connect(self._on_play_video)
        actions_row.addWidget(play_btn)

        root.addLayout(actions_row)

    def _format_file_size(self) -> str:
        try:
            if self._video_path.exists():
                size_bytes = self._video_path.stat().st_size
                if size_bytes >= 1024 * 1024:
                    return f"{size_bytes / (1024 * 1024):.2f} MB"
                if size_bytes >= 1024:
                    return f"{size_bytes / 1024:.1f} KB"
                return f"{size_bytes} Bytes"
        except Exception:
            pass
        return "Unknown size"

    def _on_copy_path(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(str(self._video_path))
            self._copy_btn.setText("Copied!")
            QTimer.singleShot(1500, lambda: self._copy_btn.setText("Copy Path"))

    def _on_play_video(self) -> None:
        """Launch video in default OS media player."""
        if self._video_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._video_path)))

    def _on_open_folder(self) -> None:
        """Reveal file in OS File Explorer."""
        folder = self._video_path.parent.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            try:
                if self._video_path.exists():
                    subprocess.Popen(f'explorer.exe /select,"{self._video_path}"')
                    return
                subprocess.Popen(f'explorer.exe "{folder}"')
                return
            except Exception:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
