"""Settings page. Pinned at the bottom of the sidebar on every mockup screen,
but no mockup was supplied for its own contents — this is a minimal static
placeholder (tool discovery status) rather than an invented full design.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from droiddesk.context import AppContext
from droiddesk.ui.theme import get_icon, get_pixmap
from droiddesk.ui.widgets.card import Card, PageHeader


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        outer.addWidget(PageHeader("Settings", "Tool discovery, environments, and test profiles."))

        card = Card("Tools")
        for name, available in self._ctx.tool_locator.discover_all().items():
            row = QHBoxLayout()
            icon_lbl = QLabel()
            icon_lbl.setFixedSize(16, 16)
            icon_lbl.setPixmap(
                get_pixmap(
                    "circle-check" if available else "circle-x",
                    size=14,
                    color="#27ae60" if available else "#e0574a",
                )
            )
            row.addWidget(icon_lbl)
            name_label = QLabel(name)
            name_label.setProperty("role", "mono")
            status_label = QLabel("found on PATH" if available else "not found")
            status_label.setProperty("role", "muted")
            row.addWidget(name_label)
            row.addStretch(1)
            row.addWidget(status_label)
            card.body_layout().addLayout(row)
        card.body_layout().addStretch(1)
        outer.addWidget(card)

        # Environments Management Card
        env_card = Card("Project Environments")
        env_service = self._ctx.env_service
        envs = env_service.load_environments() if env_service else []

        if not envs:
            empty_lbl = QLabel("No environments configured in .droiddesk/environments.toml")
            empty_lbl.setProperty("role", "muted")
            env_card.body_layout().addWidget(empty_lbl)
        else:
            for env in envs:
                row = QHBoxLayout()
                lbl = QLabel(f"{env.label} ({env.key.upper()})")
                lbl.setStyleSheet("font-weight: 600;")
                detail = QLabel(f"{env.env_file} · {env.api_host or 'no host'}")
                detail.setProperty("role", "muted")
                row.addWidget(lbl)
                row.addWidget(detail)
                row.addStretch(1)
                env_card.body_layout().addLayout(row)

        manage_btn = QPushButton("Manage Environments")
        manage_btn.setIcon(get_icon("settings-2", size=13, color="#60a5fa"))
        manage_btn.setIconSize(QSize(13, 13))
        manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #23252a;
                border: 1px solid #3b82f6;
                border-radius: 5px;
                color: #60a5fa;
                font-weight: 600;
                padding: 6px 14px;
                margin-top: 8px;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                color: #ffffff;
            }
            """
        )
        manage_btn.clicked.connect(self._open_environment_dialog)
        env_card.body_layout().addWidget(manage_btn, 0, Qt.AlignmentFlag.AlignLeft)

        outer.addWidget(env_card)
        outer.addStretch(1)

    def _open_environment_dialog(self) -> None:
        if not self._ctx.env_service:
            return
        from droiddesk.ui.dialogs.environment_dialog import EnvironmentSwitchDialog

        dlg = EnvironmentSwitchDialog(self._ctx.env_service, parent=self)
        dlg.exec()
