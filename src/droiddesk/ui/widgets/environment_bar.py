"""The always-visible active-environment indicator — Section 6.8. Spans the
top of the window next to the brand block, coloured by risk so that pointing
a release build at production is never a silent mistake.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from droiddesk.ui.theme import ENVIRONMENT_RISK_COLORS


class EnvironmentBar(QWidget):
    switch_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("environmentBar")
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 0, 0)
        layout.setSpacing(8)

        self._icon = QLabel("⛨")  # black shield
        self._icon.setObjectName("envIcon")
        self._label = QLabel("ACTIVE ENVIRONMENT")
        self._label.setObjectName("envLabel")
        self._value = QLabel()
        self._value.setObjectName("envValue")
        self._detail = QLabel()
        self._detail.setObjectName("envDetail")
        self._detail.setProperty("role", "mono")

        layout.addWidget(self._icon)
        layout.addWidget(self._label)
        layout.addWidget(self._value)
        layout.addWidget(self._detail)
        layout.addStretch(1)

        self._switch_button = QPushButton("↻  Switch environment")
        self._switch_button.setProperty("role", "outlineRed")
        self._switch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._switch_button.clicked.connect(self.switch_requested)
        layout.addWidget(self._switch_button)

        self.set_environment("production", "Production", "api.example.com", "release builds allowed")

    def set_environment(self, key: str, label: str, host: str, note: str) -> None:
        color = ENVIRONMENT_RISK_COLORS.get(key, ENVIRONMENT_RISK_COLORS["production"])
        self._value.setText(label)
        self._detail.setText(f"· {host} · {note}")
        # Qt stylesheets take alpha-hex as #AARRGGBB, not the CSS #RRGGBBAA order.
        alpha_color = f"#55{color.lstrip('#')}"
        self.setStyleSheet(f"#environmentBar {{ border-bottom: 1px solid {alpha_color}; }}")
