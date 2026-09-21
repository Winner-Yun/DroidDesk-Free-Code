"""Reusable empty state widget for pages when no APK file is active or selected.
Provides clear explanation and an action button to upload/add an APK (text and button only).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class EmptyStateWidget(QFrame):
    """Clean, modern empty state container with text and upload button (no icons)."""

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
        self._upload_btn.clicked.connect(self.upload_requested.emit)
        self._upload_btn.setVisible(show_button)

        if frameless:
            # Embedded directly inside another Card or panel — no outer frame/border
            self.setStyleSheet("#emptyStateWidget { background: transparent; border: none; }")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 4, 0, 4)
            layout.setSpacing(10)

            self._title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self._title_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #f0f2f5;")
            layout.addWidget(self._title_label)

            self._message_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self._message_label.setWordWrap(True)
            self._message_label.setStyleSheet("font-size: 12px; color: #8b8e94; line-height: 1.4;")
            layout.addWidget(self._message_label)

            self._upload_btn.setStyleSheet(
                """
                QPushButton {
                    background: #3b82f6;
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 12px;
                    padding: 7px 18px;
                    border-radius: 6px;
                    border: none;
                    margin-top: 4px;
                }
                QPushButton:hover {
                    background: #2563eb;
                }
                QPushButton:pressed {
                    background: #1d4ed8;
                }
                """
            )
            layout.addWidget(self._upload_btn, 0, Qt.AlignmentFlag.AlignLeft)

        elif compact:
            # Banner layout (used across Dashboard, Security, Commands, Organizer)
            self.setStyleSheet(
                """
                #emptyStateWidget {
                    background: #1c1d22;
                    border: 1px solid #2d3039;
                    border-radius: 8px;
                }
                """
            )
            h_layout = QHBoxLayout(self)
            h_layout.setContentsMargins(18, 12, 18, 12)
            h_layout.setSpacing(16)

            text_col = QVBoxLayout()
            text_col.setSpacing(3)

            self._title_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #f0f2f5;")
            text_col.addWidget(self._title_label)

            self._message_label.setWordWrap(True)
            self._message_label.setStyleSheet("font-size: 12px; color: #8b8e94;")
            text_col.addWidget(self._message_label)
            h_layout.addLayout(text_col, 1)

            self._upload_btn.setStyleSheet(
                """
                QPushButton {
                    background: #3b82f6;
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 12px;
                    padding: 7px 18px;
                    border-radius: 6px;
                    border: none;
                }
                QPushButton:hover {
                    background: #2563eb;
                }
                QPushButton:pressed {
                    background: #1d4ed8;
                }
                """
            )
            h_layout.addWidget(self._upload_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        else:
            # Standalone full page empty state (Analyzer, Gate, Reports)
            self.setStyleSheet(
                """
                #emptyStateWidget {
                    background: #18191c;
                    border: 1px solid #28292d;
                    border-radius: 10px;
                }
                """
            )
            layout = QVBoxLayout(self)
            layout.setContentsMargins(36, 44, 36, 44)
            layout.setSpacing(12)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._title_label.setStyleSheet("font-size: 17px; font-weight: 700; color: #f0f2f5;")
            layout.addWidget(self._title_label, 0, Qt.AlignmentFlag.AlignCenter)

            self._message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._message_label.setWordWrap(True)
            self._message_label.setMaximumWidth(500)
            self._message_label.setStyleSheet("font-size: 13px; color: #8b8e94; line-height: 1.5;")
            layout.addWidget(self._message_label, 0, Qt.AlignmentFlag.AlignCenter)

            self._upload_btn.setStyleSheet(
                """
                QPushButton {
                    background: #3b82f6;
                    color: #ffffff;
                    font-weight: 600;
                    font-size: 13px;
                    padding: 8px 24px;
                    border-radius: 6px;
                    border: none;
                    margin-top: 6px;
                }
                QPushButton:hover {
                    background: #2563eb;
                }
                QPushButton:pressed {
                    background: #1d4ed8;
                }
                """
            )
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
