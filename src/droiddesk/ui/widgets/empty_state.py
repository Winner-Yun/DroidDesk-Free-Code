"""Reusable empty state widget for pages when no APK file is active or selected.
Provides clear explanation and an action button to upload/add an APK (text and button only).
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.ui.theme import get_icon


class EmptyStateWidget(QFrame):
    """Clean, modern empty state container with text and upload button."""

    upload_requested = Signal()

    def __init__(
        self,
        title: str = "No APK File Selected",
        message: str = "Select an APK from the app bar or upload a new one to begin.",
        button_text: str = "Upload APK",
        show_button: bool = True,
        compact: bool = False,
        frameless: bool = False,
        parent: QWidget | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("emptyStateWidget")

        # Create child widgets
        self._title_label = QLabel(title)
        self._message_label = QLabel(message)
        self._upload_btn = QPushButton(button_text)
        self._upload_btn.setProperty("role", "primary")
        self._upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_btn.setIcon(get_icon("upload", size=14, color="#ffffff"))
        self._upload_btn.setIconSize(QSize(14, 14))
        self._upload_btn.clicked.connect(self.upload_requested.emit)
        self._upload_btn.setVisible(show_button)

        self.setProperty("frameless", frameless)
        self.setProperty("compact", compact)

        if frameless:
            # Embedded directly inside another Card or panel - no outer frame/border
            self._title_label.setProperty("role", "sectionTitle")
            self._title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self._message_label.setProperty("role", "muted")
            self._message_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self._message_label.setWordWrap(True)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(10)
            layout.addWidget(self._title_label)
            layout.addWidget(self._message_label)
            layout.addWidget(self._upload_btn, 0, Qt.AlignmentFlag.AlignLeft)

        elif compact:
            # Banner layout (used across Dashboard, Security, Commands, Organizer)
            self._title_label.setProperty("role", "sectionTitle")
            self._message_label.setProperty("role", "muted")
            self._message_label.setWordWrap(True)

            h_layout = QHBoxLayout(self)
            h_layout.setContentsMargins(18, 12, 18, 12)
            h_layout.setSpacing(16)

            text_col = QVBoxLayout()
            text_col.setSpacing(3)
            text_col.addWidget(self._title_label)
            text_col.addWidget(self._message_label)
            h_layout.addLayout(text_col, 1)
            h_layout.addWidget(self._upload_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        else:
            # Standalone full page empty state (Analyzer, Gate, Reports, Screenshots)
            self._title_label.setProperty("role", "pageTitle")
            self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._message_label.setProperty("role", "muted")
            self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._message_label.setWordWrap(True)
            self._message_label.setFixedWidth(520)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(36, 44, 36, 44)
            layout.setSpacing(12)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._title_label, 0, Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._message_label, 0, Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._upload_btn, 0, Qt.AlignmentFlag.AlignCenter)

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def set_message(self, message: str) -> None:
        self._message_label.setText(message)

    def set_icon(self, icon: str) -> None:
        # Icons removed as per user preference
        pass

    def set_button_visible(self, visible: bool) -> None:
        self._upload_btn.setVisible(visible)

    def set_theme(self, mode: str) -> None:
        self._upload_btn.setIcon(get_icon("upload", size=14, color="#ffffff"))

