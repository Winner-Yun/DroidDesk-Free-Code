"""The active-environment indicator and appbar APK management controls.

Spans the top of the window next to the brand block, displaying the active environment,
the active APK selector dropdown, and the single system-wide APK upload action.
"""

from __future__ import annotations

from pathlib import Path
from typing import override

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QWidget,
)

from droiddesk.config import Settings
from droiddesk.services.apk_service import ApkService
from droiddesk.ui.theme import ENVIRONMENT_RISK_COLORS, get_icon


class EnvironmentBar(QWidget):
    switch_requested = Signal()
    apk_selected = Signal(object)  # Path | None
    apks_uploaded = Signal(list)  # list[Path]

    def __init__(
        self,
        apk_service: ApkService | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__()
        self._apk_service = apk_service
        self._settings = settings

        self.setObjectName("environmentBar")
        self.setFixedHeight(52)
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 16, 0)
        layout.setSpacing(8)

        # Active APK selector dropdown
        apk_tag = QLabel("APK:")
        apk_tag.setStyleSheet("font-weight: 700; font-size: 11px; color: #8b8e94;")
        layout.addWidget(apk_tag)

        self._apk_selector = QComboBox()
        self._apk_selector.setObjectName("apkSelector")
        self._apk_selector.setMinimumWidth(190)
        self._apk_selector.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apk_selector.addItem("No APK selected", None)
        self._apk_selector.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._apk_selector.customContextMenuRequested.connect(self._on_selector_context_menu)
        self._apk_selector.currentIndexChanged.connect(self._on_apk_combo_changed)
        layout.addWidget(self._apk_selector)

        # Remove APK button
        self._remove_button = QPushButton("Remove")
        self._remove_button.setObjectName("apkRemoveButton")
        self._remove_button.setIcon(get_icon("trash-2", size=12, color="#e0574a"))
        self._remove_button.setIconSize(QSize(12, 12))
        self._remove_button.setToolTip("Remove active APK from project")
        self._remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_button.setEnabled(False)
        self._remove_button.setStyleSheet(
            """
            QPushButton#apkRemoveButton {
                background-color: rgba(224, 87, 74, 0.08);
                border: 1px solid rgba(224, 87, 74, 0.4);
                border-radius: 5px;
                color: #e0574a;
                font-size: 12px;
                font-weight: 600;
                padding: 5px 12px;
            }
            QPushButton#apkRemoveButton:hover {
                background-color: #e0574a;
                border-color: #e0574a;
                color: #ffffff;
            }
            QPushButton#apkRemoveButton:disabled {
                background-color: transparent;
                border-color: #27282d;
                color: #4a2828;
            }
            """
        )
        self._remove_button.clicked.connect(self._on_remove_clicked)
        layout.addWidget(self._remove_button)

        layout.addSpacing(4)

        # Appbar Upload APK button
        self._upload_button = QPushButton("Upload APK")
        self._upload_button.setProperty("role", "primary")
        self._upload_button.setIcon(get_icon("upload", size=14, color="#ffffff"))
        self._upload_button.setIconSize(QSize(14, 14))
        self._upload_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_button.setToolTip("Upload or Add one or multiple APK / AAB files")
        self._upload_button.clicked.connect(self._on_upload_clicked)
        layout.addWidget(self._upload_button)

        layout.addStretch(1)

        # Active environment indicator button (removed from appbar per user request)
        self._env_button = QPushButton()
        self._env_button.setObjectName("envBadgeButton")
        self._env_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._env_button.setToolTip("Click to switch project environment")
        self._env_button.clicked.connect(self.switch_requested.emit)
        self._env_button.hide()
        self.set_environment(None)

        self._load_apks_from_db()

    def _load_apks_from_db(self) -> None:
        """Populate selector from the database and restore active setting."""
        if not self._apk_service:
            return

        apks = self._apk_service.list_apks()
        if not apks:
            return

        self._apk_selector.blockSignals(True)
        self._apk_selector.clear()

        preferred_hash = self._settings.active_apk_hash if self._settings else None
        target_idx = -1

        for idx, apk in enumerate(apks):
            label = apk.file_path.name
            self._apk_selector.addItem(label, apk.file_path)
            self._apk_selector.setItemData(idx, apk.file_hash, Qt.ItemDataRole.UserRole + 1)
            if preferred_hash and apk.file_hash == preferred_hash:
                target_idx = idx

        if target_idx < 0 and self._apk_selector.count() > 0:
            target_idx = 0

        if target_idx >= 0:
            self._apk_selector.setCurrentIndex(target_idx)
            self._remove_button.setEnabled(True)
            if self._settings:
                sel_hash = self._apk_selector.itemData(target_idx, Qt.ItemDataRole.UserRole + 1)
                self._settings.active_apk_hash = sel_hash if isinstance(sel_hash, str) else None
                self._settings.save()
        else:
            self._remove_button.setEnabled(False)

        self._apk_selector.blockSignals(False)
        self._remove_button.setEnabled(self.selected_apk() is not None)

    def set_environment(self, env_or_key: object | None) -> None:
        """Update the environment indicator button and bottom border."""
        from droiddesk.core.profiles import Environment

        if isinstance(env_or_key, Environment):
            key = env_or_key.key
            label = env_or_key.label
            host = env_or_key.api_host or ""
            note = "Release permitted" if env_or_key.allow_release_build else "Release blocked"
            color = ENVIRONMENT_RISK_COLORS.get(key, "#8b8e94")
            alpha_color = f"#55{color.lstrip('#')}"
            self.setStyleSheet(f"#environmentBar {{ border-bottom: 1px solid {alpha_color}; }}")

            host_part = f" · {host}" if host else ""
            note_part = f" [{note}]" if note else ""
            btn_text = f"● {label.upper()} ({key}){host_part}{note_part}"
            self._env_button.setText(btn_text)
            self._env_button.setStyleSheet(
                f"""
                QPushButton#envBadgeButton {{
                    background-color: {color}22;
                    border: 1px solid {color}88;
                    border-radius: 4px;
                    color: {color};
                    font-size: 11px;
                    font-weight: 700;
                    padding: 4px 10px;
                }}
                QPushButton#envBadgeButton:hover {{
                    background-color: {color}44;
                    border-color: {color};
                }}
                """
            )
        elif isinstance(env_or_key, str) and env_or_key:
            key = env_or_key
            label = key.capitalize()
            color = ENVIRONMENT_RISK_COLORS.get(key, "#8b8e94")
            alpha_color = f"#55{color.lstrip('#')}"
            self.setStyleSheet(f"#environmentBar {{ border-bottom: 1px solid {alpha_color}; }}")
            btn_text = f"● {label.upper()} ({key})"
            self._env_button.setText(btn_text)
            self._env_button.setStyleSheet(
                f"""
                QPushButton#envBadgeButton {{
                    background-color: {color}22;
                    border: 1px solid {color}88;
                    border-radius: 4px;
                    color: {color};
                    font-size: 11px;
                    font-weight: 700;
                    padding: 4px 10px;
                }}
                QPushButton#envBadgeButton:hover {{
                    background-color: {color}44;
                    border-color: {color};
                }}
                """
            )
        else:
            self.setStyleSheet("#environmentBar { border-bottom: 1px solid #27282d; }")
            self._env_button.setText("● No Environment  [Configure]")
            self._env_button.setStyleSheet(
                """
                QPushButton#envBadgeButton {
                    background-color: rgba(139, 142, 148, 0.12);
                    border: 1px dashed #8b8e94;
                    border-radius: 4px;
                    color: #9ca3af;
                    font-size: 11px;
                    font-weight: 600;
                    padding: 4px 10px;
                }
                QPushButton#envBadgeButton:hover {
                    background-color: rgba(91, 155, 213, 0.18);
                    border-color: #5b9bd5;
                    color: #5b9bd5;
                }
                """
            )

    def selected_apk(self) -> Path | None:
        data = self._apk_selector.currentData()
        return data if isinstance(data, Path) else None

    def selected_apk_hash(self) -> str | None:
        idx = self._apk_selector.currentIndex()
        if idx < 0:
            return None
        val = self._apk_selector.itemData(idx, Qt.ItemDataRole.UserRole + 1)
        return str(val) if val else None

    def apk_selector(self) -> QComboBox:
        return self._apk_selector

    def add_and_select_apks(self, paths: list[Path]) -> None:
        if not paths:
            return

        imported_items: list[tuple[Path, str | None]] = []
        for p in paths:
            if self._apk_service:
                try:
                    info = self._apk_service.import_apk(p)
                    imported_items.append((info.file_path, info.file_hash))
                except Exception:
                    imported_items.append((p, None))
            else:
                imported_items.append((p, None))

        # Remove placeholder if present
        if self._apk_selector.count() == 1 and self._apk_selector.itemData(0) is None:
            self._apk_selector.removeItem(0)

        existing_paths = [self._apk_selector.itemData(i) for i in range(self._apk_selector.count())]

        target_idx = -1
        for p, file_hash in imported_items:
            if p not in existing_paths:
                label = p.name
                idx = self._apk_selector.count()
                self._apk_selector.addItem(label, p)
                if file_hash:
                    self._apk_selector.setItemData(idx, file_hash, Qt.ItemDataRole.UserRole + 1)
                existing_paths.append(p)
            target_idx = existing_paths.index(p)

        if target_idx >= 0:
            self._apk_selector.setCurrentIndex(target_idx)
            self._remove_button.setEnabled(True)

        self.apks_uploaded.emit([item[0] for item in imported_items])

    def _on_apk_combo_changed(self, _index: int) -> None:
        path = self.selected_apk()
        apk_hash = self.selected_apk_hash()
        self._remove_button.setEnabled(path is not None)
        if self._settings:
            self._settings.active_apk_hash = apk_hash
            self._settings.save()
        self.apk_selected.emit(path)

    def _on_remove_clicked(self) -> None:
        path = self.selected_apk()
        if not path:
            return

        apk_hash = self.selected_apk_hash()

        msg = (
            f"Remove '{path.name}' from the project?\n\n"
            "This removes its database record and cached copy."
        )
        reply = QMessageBox.question(
            self,
            "Remove APK",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self._apk_service and apk_hash:
            self._apk_service.remove_apk(apk_hash)

        curr_idx = self._apk_selector.currentIndex()
        if curr_idx >= 0:
            self._apk_selector.removeItem(curr_idx)

        if self._apk_selector.count() == 0:
            self._apk_selector.addItem("No APK selected", None)
            self._remove_button.setEnabled(False)
            if self._settings:
                self._settings.active_apk_hash = None
                self._settings.save()
            self.apk_selected.emit(None)
        else:
            self._apk_selector.setCurrentIndex(0)

    def _on_selector_context_menu(self, pos: QPoint) -> None:
        if not self.selected_apk():
            return
        menu = QMenu(self)
        remove_action = menu.addAction("Remove from project")
        remove_action.triggered.connect(self._on_remove_clicked)
        menu.exec(self._apk_selector.mapToGlobal(pos))

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
