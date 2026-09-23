"""OverrideDialog: Dialog requiring a typed reason to bypass blocking guards/checks.

Per Section 6.9 & 6.10:
A blocking check can only be bypassed through a dialog that requires typing
a reason, permanently recorded in build_record. Visible-but-possible beats
impossible - making it impossible just drives people around the tool.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.ui.theme import get_icon


class OverrideDialog(QDialog):
    """Dialog forcing user to record an explicit audit reason before bypassing a check."""

    def __init__(
        self,
        failed_items: list[str],
        title: str = "Bypass Guard Failure",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.setStyleSheet("""
            QDialog {
                background: #141517;
                color: #e4e4e7;
                border: 1px solid #27272a;
                border-radius: 8px;
            }
            QLabel[role="header"] {
                font-size: 16px;
                font-weight: 700;
                color: #f43f5e;
            }
            QLabel[role="warningBox"] {
                background: rgba(244, 63, 94, 0.1);
                border: 1px solid rgba(244, 63, 94, 0.3);
                border-radius: 6px;
                padding: 10px;
                color: #fca5a5;
                font-size: 12px;
            }
            QPlainTextEdit {
                background: #1c1d21;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                color: #f4f4f5;
                padding: 8px;
                font-size: 13px;
            }
            QPlainTextEdit:focus {
                border: 1px solid #6366f1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Override Blocking Guard")
        header.setProperty("role", "header")
        layout.addWidget(header)

        items_text = ", ".join(failed_items)
        warn_box = QLabel(
            f"The following blocking check(s) failed:\n• {items_text}\n\n"
            "Bypassing this safety guard will be permanently logged in the "
            "build audit history with your reason."
        )
        warn_box.setWordWrap(True)
        warn_box.setProperty("role", "warningBox")
        layout.addWidget(warn_box)

        reason_label = QLabel("Reason for override (required):")
        reason_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #a1a1aa;")
        layout.addWidget(reason_label)

        self._reason_edit = QPlainTextEdit()
        self._reason_edit.setPlaceholderText("e.g., Emergency hotfix approved by SecOps...")
        self._reason_edit.setFixedHeight(90)
        self._reason_edit.textChanged.connect(self._validate)
        layout.addWidget(self._reason_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("role", "secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._confirm_btn = QPushButton("Confirm Override && Proceed")
        self._confirm_btn.setProperty("role", "primary")
        self._confirm_btn.setIcon(get_icon("shield-alert", size=13, color="#ffffff"))
        self._confirm_btn.setIconSize(QSize(13, 13))
        self._confirm_btn.setStyleSheet("""
            QPushButton {
                background: #e11d48;
                color: #ffffff;
                font-weight: 600;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #f43f5e;
            }
            QPushButton:disabled {
                background: #4c1d25;
                color: #888888;
            }
        """)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._confirm_btn)

        layout.addLayout(btn_row)

    def _validate(self) -> None:
        has_reason = bool(self._reason_edit.toPlainText().strip())
        self._confirm_btn.setEnabled(has_reason)

    def reason(self) -> str:
        return self._reason_edit.toPlainText().strip()
