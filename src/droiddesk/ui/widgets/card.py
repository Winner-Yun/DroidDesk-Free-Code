"""Generic bordered panel used to group content on every page (the "Needs
attention" / "Recent runs" boxes on the Dashboard, the detail panel on
Devices, etc.), plus the small stat tile used at the top of the Dashboard.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class Card(QFrame):
    """Bordered rounded panel with an optional title row."""

    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(10)
        if title:
            heading = QLabel(title)
            heading.setProperty("role", "sectionTitle")
            heading.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._layout.addWidget(heading)

    def body_layout(self) -> QVBoxLayout:
        return self._layout


class StatCard(QFrame):
    """Big-number tile, e.g. the four cards at the top of the Dashboard."""

    def __init__(self, value: str, label: str) -> None:
        super().__init__()
        self.setProperty("role", "statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setProperty("role", "statNumber")
        self.caption = QLabel(label)
        self.caption.setProperty("role", "muted")
        layout.addWidget(self.value_label)
        layout.addWidget(self.caption)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

    def set_caption(self, caption: str) -> None:
        self.caption.setText(caption)


class PageHeader(QWidget):
    """Title + subtitle on the left, action buttons on the right - the row
    that opens every page in the mockups.
    """

    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_label = QLabel(title)
        title_label.setProperty("role", "pageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setProperty("role", "pageSubtitle")
        subtitle_label.setWordWrap(True)
        text_col.addWidget(title_label)
        text_col.addWidget(subtitle_label)

        outer.addLayout(text_col, 1)

        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(8)
        outer.addLayout(self.actions_layout)

    def add_action(self, button: QWidget) -> None:
        self.actions_layout.addWidget(button)
