"""The active-environment indicator and appbar APK management controls.

Spans the top of the window next to the brand block, displaying the active environment,
the active APK selector dropdown, and the single system-wide APK upload action.
"""

from __future__ import annotations

from pathlib import Path
from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from droiddesk.ui.theme import ENVIRONMENT_RISK_COLORS


class EnvironmentBar(QWidget):
    switch_requested = Signal()
    apk_selected = Signal(object)  # Path | None
    apks_uploaded = Signal(list)  # list[Path]

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("environmentBar")
        self.setFixedHeight(52)
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 16, 0)
        layout.setSpacing(10)

        # Active APK selector dropdown and upload button (in place of removed environment label)
        apk_tag = QLabel("⛁  APK:")
        apk_tag.setStyleSheet("font-weight: 700; font-size: 11px; color: #8b8e94;")
        layout.addWidget(apk_tag)

        self._apk_selector = QComboBox()
        self._apk_selector.setObjectName("apkSelector")
        self._apk_selector.setMinimumWidth(180)
        self._apk_selector.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apk_selector.addItem("No APK selected", None)
        self._apk_selector.currentIndexChanged.connect(self._on_apk_combo_changed)
        layout.addWidget(self._apk_selector)

        # Appbar Upload APK button
        self._upload_button = QPushButton("Upload APK")
        self._upload_button.setProperty("role", "primary")
        self._upload_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_button.setToolTip("Upload or Add one or multiple APK / AAB files")
        self._upload_button.clicked.connect(self._on_upload_clicked)
        layout.addWidget(self._upload_button)

        layout.addStretch(1)

    def set_environment(
        self, key: str, label: str = "", host: str = "", note: str = ""
    ) -> None:
        color = ENVIRONMENT_RISK_COLORS.get(key, ENVIRONMENT_RISK_COLORS["production"])
        # Qt stylesheets take alpha-hex as #AARRGGBB, not the CSS #RRGGBBAA order.
        alpha_color = f"#55{color.lstrip('#')}"
        self.setStyleSheet(f"#environmentBar {{ border-bottom: 1px solid {alpha_color}; }}")

    def selected_apk(self) -> Path | None:
        data = self._apk_selector.currentData()
        return data if isinstance(data, Path) else None

    def apk_selector(self) -> QComboBox:
        return self._apk_selector

    def add_and_select_apks(self, paths: list[Path]) -> None:
        if not paths:
            return

        # Remove placeholder if present
        if self._apk_selector.count() == 1 and self._apk_selector.itemData(0) is None:
            self._apk_selector.removeItem(0)

        existing_paths = [
            self._apk_selector.itemData(i)
            for i in range(self._apk_selector.count())
        ]

        target_idx = -1
        for p in paths:
            if p not in existing_paths:
                label = f"⛁  {p.name}"
                self._apk_selector.addItem(label, p)
                existing_paths.append(p)
            target_idx = existing_paths.index(p)

        if target_idx >= 0:
            self._apk_selector.setCurrentIndex(target_idx)

        self.apks_uploaded.emit(paths)

    def _on_apk_combo_changed(self, _index: int) -> None:
        self.apk_selected.emit(self.selected_apk())

    def _on_upload_clicked(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select APK Files to Upload",
            "",
            "Android Packages (*.apk *.aab);;All Files (*)",
        )
        if files:
            self.add_and_select_apks([Path(f) for f in files])

    @override
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(u.toLocalFile().lower().endswith((".apk", ".aab")) for u in urls):
                event.acceptProposedAction()
                return
        event.ignore()

    @override
    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            Path(u.toLocalFile())
            for u in event.mimeData().urls()
            if u.toLocalFile().lower().endswith((".apk", ".aab"))
        ]
        if paths:
            event.acceptProposedAction()
            self.add_and_select_apks(paths)
        else:
            event.ignore()
