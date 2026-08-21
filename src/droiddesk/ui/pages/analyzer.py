"""APK Analyzer page — Section 6.2. Identity, Signature, Permissions, Components,
Size, Native libs, and Compare panels. Panels load lazily — full androguard
analysis only runs when a panel that needs it is opened.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

_PANELS = ("Identity", "Signature", "Permissions", "Components", "Size", "Native libs", "Compare")


class AnalyzerPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("APK Analyzer — Phase 2"))
        tabs = QTabWidget()
        for name in _PANELS:
            placeholder = QLabel(f"{name} — populated on APK load")
            tabs.addTab(placeholder, name)
        layout.addWidget(tabs)
