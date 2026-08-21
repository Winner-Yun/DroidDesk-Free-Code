"""Settings page. Pinned at the bottom of the sidebar on every mockup screen,
but no mockup was supplied for its own contents — this is a minimal static
placeholder (tool discovery status) rather than an invented full design.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from droiddesk.ui import static_data
from droiddesk.ui.widgets.card import Card, PageHeader


class SettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        outer.addWidget(PageHeader("Settings", "Tool discovery, environments, and test profiles."))

        card = Card("Tools")
        for name, available in static_data.TOOL_STATUS:
            row = QHBoxLayout()
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
        outer.addStretch(1)

    # TODO(Phase 1+): tool path overrides bound to Settings.load()/save(),
    # environment editor, test-profile editor.
