"""Settings page: toolchain management, active environment, storage & cache, and legal limits.

Refactored from static placeholder into a functional configuration and diagnostic hub.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import PySide6
from PySide6.QtCore import QSize, Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.ui.dialogs.setup_dialog import SetupDialog
from droiddesk.ui.theme import (
    BORDER_LIGHT,
    ENVIRONMENT_RISK_COLORS,
    TEXT_MUTED,
    get_icon,
)
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.status_pill import StatusPill

_STATEMENT_OF_LIMITATIONS = (
    "DroidDesk performs automated checks for commonly misplaced configuration and "
    "credential files. It detects accidental exposure, not deliberate concealment. "
    "A clean result indicates that no issues were found by the checks performed; "
    "it is not a guarantee that an application is secure, and it does not substitute "
    "for security review."
)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.setProperty("role", "page")

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # Scrollable container for the settings cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        layout.addWidget(
            PageHeader(
                "Settings & Diagnostics",
                "Toolchain verification, SDK overrides, environment safety, and storage.",
            )
        )

        # 1. Toolchain & Android SDK
        layout.addWidget(self._build_toolchain_card())

        # 2. Environments & Safety Defaults
        layout.addWidget(self._build_environments_card())

        # 3. Storage & Cache Maintenance
        layout.addWidget(self._build_storage_card())

        # 4. About & Statement of Limitations
        layout.addWidget(self._build_about_card())

        layout.addStretch(1)
        scroll.setWidget(container)
        page_layout.addWidget(scroll)

        # Initial data population
        self._refresh_tools()
        self._refresh_storage_stats()

    # -- 1. Toolchain & Android SDK Card --------------------------------------

    def _build_toolchain_card(self) -> Card:
        card = Card("Toolchain & Android SDK")
        body = card.body_layout()

        # Path Configuration Controls
        path_box = QFrame()
        path_box.setStyleSheet(
            f"background-color: #1e1f23; border: 1px solid {BORDER_LIGHT}; "
            "border-radius: 6px; padding: 10px;"
        )
        box_layout = QVBoxLayout(path_box)
        box_layout.setContentsMargins(10, 8, 10, 8)
        box_layout.setSpacing(8)

        # Android SDK Row
        sdk_row = QHBoxLayout()
        sdk_lbl = QLabel("Android SDK:")
        sdk_lbl.setFixedWidth(90)
        sdk_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        self._sdk_input = QLineEdit()
        self._sdk_input.setPlaceholderText("Auto-detected via ANDROID_HOME or standard paths")
        if self._ctx.settings.android_sdk_path:
            self._sdk_input.setText(str(self._ctx.settings.android_sdk_path))

        sdk_browse_btn = QPushButton("Browse...")
        sdk_browse_btn.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        sdk_browse_btn.clicked.connect(self._on_browse_sdk)

        sdk_save_btn = QPushButton("Save")
        sdk_save_btn.setStyleSheet("padding: 4px 12px; font-size: 11px; font-weight: 600;")
        sdk_save_btn.clicked.connect(self._on_save_sdk_path)

        sdk_row.addWidget(sdk_lbl)
        sdk_row.addWidget(self._sdk_input, 1)
        sdk_row.addWidget(sdk_browse_btn)
        sdk_row.addWidget(sdk_save_btn)
        box_layout.addLayout(sdk_row)

        # Java Home Row
        java_row = QHBoxLayout()
        java_lbl = QLabel("Java Home:")
        java_lbl.setFixedWidth(90)
        java_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        self._java_input = QLineEdit()
        self._java_input.setPlaceholderText("Auto-detected via JAVA_HOME or Android Studio JBR")
        if self._ctx.settings.java_home_path:
            self._java_input.setText(str(self._ctx.settings.java_home_path))

        java_browse_btn = QPushButton("Browse...")
        java_browse_btn.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        java_browse_btn.clicked.connect(self._on_browse_java)

        java_save_btn = QPushButton("Save")
        java_save_btn.setStyleSheet("padding: 4px 12px; font-size: 11px; font-weight: 600;")
        java_save_btn.clicked.connect(self._on_save_java_path)

        java_row.addWidget(java_lbl)
        java_row.addWidget(self._java_input, 1)
        java_row.addWidget(java_browse_btn)
        java_row.addWidget(java_save_btn)
        box_layout.addLayout(java_row)

        body.addWidget(path_box)

        # Action Toolbar (Verify All Tools + Run Setup Wizard)
        action_bar = QHBoxLayout()
        verify_btn = QPushButton("Verify All Tools")
        verify_btn.setIcon(get_icon("refresh-cw", size=13, color="#60a5fa"))
        verify_btn.setIconSize(QSize(13, 13))
        verify_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #23252a;
                border: 1px solid #3b82f6;
                border-radius: 4px;
                color: #60a5fa;
                font-weight: 600;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                color: #ffffff;
            }
            """
        )
        verify_btn.clicked.connect(self._on_verify_all_tools)
        action_bar.addWidget(verify_btn)

        wizard_btn = QPushButton("Run Setup Wizard")
        wizard_btn.setIcon(get_icon("wrench", size=13, color="#e5e7eb"))
        wizard_btn.setIconSize(QSize(13, 13))
        wizard_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2a2c31;
                border: 1px solid #35373e;
                border-radius: 4px;
                color: #e5e7eb;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #35373e;
            }
            """
        )
        wizard_btn.clicked.connect(self._on_run_setup_wizard)
        action_bar.addWidget(wizard_btn)

        self._tool_status_feedback = QLabel("")
        self._tool_status_feedback.setStyleSheet("color: #8b8e94; font-size: 11px;")
        action_bar.addWidget(self._tool_status_feedback)
        action_bar.addStretch(1)

        body.addLayout(action_bar)

        # Tool Status Table
        self._tool_table = QTableWidget(0, 5)
        self._tool_table.setHorizontalHeaderLabels(
            ["Tool", "Status", "Version", "Path", "Actions"]
        )
        tbl_hdr = self._tool_table.horizontalHeader()
        tbl_hdr.setStretchLastSection(False)
        tbl_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tbl_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tbl_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tbl_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        tbl_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._tool_table.verticalHeader().setVisible(False)
        self._tool_table.setShowGrid(False)
        self._tool_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tool_table.setMinimumHeight(280)
        self._tool_table.setStyleSheet(
            """
            QTableWidget {
                background-color: #1a1b1e;
                border: 1px solid #2c2d33;
                border-radius: 6px;
            }
            QHeaderView::section {
                background-color: #212226;
                color: #8b8e94;
                font-size: 11px;
                font-weight: 600;
                border: none;
                border-bottom: 1px solid #2c2d33;
                padding: 6px 8px;
            }
            """
        )
        body.addWidget(self._tool_table)

        return card

    def _on_browse_sdk(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Android SDK Directory",
            self._sdk_input.text().strip() or str(Path.home()),
        )
        if folder:
            self._sdk_input.setText(folder)
            self._on_save_sdk_path()

    def _on_save_sdk_path(self) -> None:
        val = self._sdk_input.text().strip()
        self._ctx.settings.android_sdk_path = Path(val) if val else None
        self._ctx.settings.save()
        self._notify_services_and_refresh()

    def _on_browse_java(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Java Home Directory",
            self._java_input.text().strip() or str(Path.home()),
        )
        if folder:
            self._java_input.setText(folder)
            self._on_save_java_path()

    def _on_save_java_path(self) -> None:
        val = self._java_input.text().strip()
        self._ctx.settings.java_home_path = Path(val) if val else None
        self._ctx.settings.save()
        self._notify_services_and_refresh()

    def _on_verify_all_tools(self) -> None:
        self._notify_services_and_refresh()
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._tool_status_feedback.setText(f"All tools verified actively at {now}.")

    def _on_run_setup_wizard(self) -> None:
        dlg = SetupDialog(self._ctx.settings, self._ctx.tool_locator, parent=self)
        if dlg.exec():
            if self._ctx.settings.android_sdk_path:
                self._sdk_input.setText(str(self._ctx.settings.android_sdk_path))
            self._notify_services_and_refresh()

    def _notify_services_and_refresh(self) -> None:
        self._ctx.tool_locator.invalidate_cache()

        # Update adb client in DeviceService
        try:
            new_adb = self._ctx.tool_locator.resolve("adb")
            self._ctx.device_service.adb_client.set_adb_path(new_adb)
            self._ctx.device_service.refresh()
        except Exception:
            pass

        # Update apkanalyzer in ApkService
        try:
            new_apkanalyzer = self._ctx.tool_locator.resolve("apkanalyzer")
            self._ctx.apk_service.set_apkanalyzer_path(new_apkanalyzer)
        except Exception:
            pass

        self._refresh_tools()

    def _refresh_tools(self) -> None:
        tool_infos = self._ctx.tool_locator.verify_all()
        self._tool_table.setRowCount(len(tool_infos))

        for row_idx, (name, info) in enumerate(tool_infos.items()):
            # Col 0: Tool Name
            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._tool_table.setItem(row_idx, 0, name_item)

            # Col 1: Status Pill
            pill_widget = QWidget()
            pill_layout = QHBoxLayout(pill_widget)
            pill_layout.setContentsMargins(6, 4, 6, 4)
            pill_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

            if info.is_bundled:
                pill = StatusPill("Bundled", "info")
            elif info.is_valid:
                pill = StatusPill("Found", "pass")
            else:
                pill = StatusPill("Missing", "fail")

            pill_layout.addWidget(pill)
            self._tool_table.setCellWidget(row_idx, 1, pill_widget)

            # Col 2: Version
            ver_text = info.version or "-"
            if not info.is_valid and info.error_message and "Java runtime" in info.error_message:
                ver_text = "Java Required"
            ver_item = QTableWidgetItem(ver_text)
            ver_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            ver_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if not info.is_valid and info.error_message and "Java runtime" in info.error_message:
                ver_item.setToolTip(info.error_message)
            self._tool_table.setItem(row_idx, 2, ver_item)

            # Col 3: Path
            path_str = str(info.path) if info.path else "(not found)"
            path_item = QTableWidgetItem(path_str)
            path_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            path_item.setToolTip(path_str)
            path_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if not info.path:
                path_item.setForeground(Qt.GlobalColor.darkGray)
            self._tool_table.setItem(row_idx, 3, path_item)

            # Col 4: Actions (Browse... / Reset)
            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            browse_btn = QPushButton("Browse...")
            browse_btn.setStyleSheet(
                "padding: 2px 8px; font-size: 11px; background-color: #212226; "
                "border: 1px solid #35373e; border-radius: 3px;"
            )
            browse_btn.clicked.connect(lambda _=None, t=name: self._on_override_tool(t))
            act_layout.addWidget(browse_btn)

            has_override = getattr(self._ctx.settings, f"{name}_path", None) is not None
            if has_override:
                reset_btn = QPushButton("Reset")
                reset_btn.setStyleSheet(
                    "padding: 2px 8px; font-size: 11px; background-color: #2a1418; "
                    "color: #e0574a; border: 1px solid #4a2226; border-radius: 3px;"
                )
                reset_btn.clicked.connect(lambda _=None, t=name: self._on_reset_tool(t))
                act_layout.addWidget(reset_btn)

            act_layout.addStretch(1)
            self._tool_table.setCellWidget(row_idx, 4, act_widget)

    def _on_override_tool(self, tool_name: str) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Executable for {tool_name}",
            str(Path.home()),
            "Executables (*.exe *.bat *.cmd *.jar);;All Files (*.*)",
        )
        if file_path:
            setattr(self._ctx.settings, f"{tool_name}_path", Path(file_path))
            self._ctx.settings.save()
            self._notify_services_and_refresh()

    def _on_reset_tool(self, tool_name: str) -> None:
        setattr(self._ctx.settings, f"{tool_name}_path", None)
        self._ctx.settings.save()
        self._notify_services_and_refresh()

    # -- 2. Environments & Safety Defaults Card -------------------------------

    def _build_environments_card(self) -> Card:
        self._env_card = Card("Environments & Safety Defaults")
        self._refresh_environments()
        return self._env_card

    def _refresh_environments(self) -> None:
        layout = self._env_card.body_layout()
        # Clear previous widgets
        while layout.count():
            item = layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()
                else:
                    sub_lay = item.layout()
                    if sub_lay is not None:
                        sub_lay.deleteLater()

        env_service = self._ctx.env_service
        active_env = env_service.active_environment() if env_service else None

        active_box = QFrame()
        active_box.setStyleSheet(
            f"background-color: #1e1f23; border: 1px solid {BORDER_LIGHT}; "
            "border-radius: 6px; padding: 12px;"
        )
        box_layout = QVBoxLayout(active_box)
        box_layout.setContentsMargins(12, 10, 12, 10)
        box_layout.setSpacing(6)

        if active_env:
            top_row = QHBoxLayout()
            title_lbl = QLabel(f"Active Environment: <b>{active_env.label}</b>")
            title_lbl.setStyleSheet("font-size: 13px; color: #ffffff;")
            top_row.addWidget(title_lbl)

            risk_color = ENVIRONMENT_RISK_COLORS.get(active_env.key.lower(), "#27ae60")
            risk_pill = QLabel(active_env.key.upper())
            risk_pill.setStyleSheet(
                f"background-color: {risk_color}; color: #ffffff; font-weight: 700; "
                "font-size: 10px; border-radius: 3px; padding: 2px 7px;"
            )
            top_row.addWidget(risk_pill)
            top_row.addStretch(1)
            box_layout.addLayout(top_row)

            rel_allowed = "Allowed" if active_env.allow_release_build else "Blocked (Lock)"
            detail_lbl = QLabel(
                f"Config: <code>{active_env.env_file}</code> · "
                f"API Host: {active_env.api_host or 'None'} · "
                f"Release Build: {rel_allowed}"
            )
            detail_lbl.setStyleSheet("color: #9ca3af; font-size: 11px;")
            box_layout.addWidget(detail_lbl)
        else:
            no_env_lbl = QLabel("No active environment selected or configured.")
            no_env_lbl.setStyleSheet("color: #8b8e94; font-size: 12px;")
            box_layout.addWidget(no_env_lbl)

        layout.addWidget(active_box)

        manage_btn = QPushButton("Manage & Switch Environments")
        manage_btn.setIcon(get_icon("settings-2", size=13, color="#60a5fa"))
        manage_btn.setIconSize(QSize(13, 13))
        manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #23252a;
                border: 1px solid #3b82f6;
                border-radius: 4px;
                color: #60a5fa;
                font-weight: 600;
                padding: 6px 14px;
                font-size: 12px;
                margin-top: 4px;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                color: #ffffff;
            }
            """
        )
        manage_btn.clicked.connect(self._open_environment_dialog)
        layout.addWidget(manage_btn, 0, Qt.AlignmentFlag.AlignLeft)

    def _open_environment_dialog(self) -> None:
        if not self._ctx.env_service:
            return
        from droiddesk.ui.dialogs.environment_dialog import EnvironmentSwitchDialog

        dlg = EnvironmentSwitchDialog(self._ctx.env_service, parent=self)
        dlg.exec()
        self._refresh_environments()

    # -- 3. Storage & Cache Maintenance Card ----------------------------------

    def _build_storage_card(self) -> Card:
        card = Card("Storage & Cache Maintenance")
        body = card.body_layout()

        grid_frame = QFrame()
        grid_frame.setStyleSheet(
            f"background-color: #1e1f23; border: 1px solid {BORDER_LIGHT}; "
            "border-radius: 6px; padding: 12px;"
        )
        grid_layout = QVBoxLayout(grid_frame)
        grid_layout.setContentsMargins(12, 10, 12, 10)
        grid_layout.setSpacing(10)

        # Database Row
        db_row = QHBoxLayout()
        db_icon = QLabel()
        db_icon.setPixmap(get_icon("database", size=14, color="#60a5fa").pixmap(14, 14))
        db_row.addWidget(db_icon)

        db_col = QVBoxLayout()
        db_col.setSpacing(2)
        db_title = QLabel("Local SQLite Database")
        db_title.setStyleSheet("font-weight: 600; font-size: 12px; color: #ffffff;")
        self._db_info_lbl = QLabel("Calculating...")
        self._db_info_lbl.setStyleSheet("color: #8b8e94; font-size: 11px;")
        db_col.addWidget(db_title)
        db_col.addWidget(self._db_info_lbl)
        db_row.addLayout(db_col, 1)

        vacuum_btn = QPushButton("Vacuum DB")
        vacuum_btn.setStyleSheet("padding: 4px 12px; font-size: 11px;")
        vacuum_btn.clicked.connect(self._on_vacuum_db)
        db_row.addWidget(vacuum_btn)
        grid_layout.addLayout(db_row)

        # APK Cache Row
        apk_row = QHBoxLayout()
        apk_icon = QLabel()
        apk_icon.setPixmap(get_icon("smartphone", size=14, color="#27ae60").pixmap(14, 14))
        apk_row.addWidget(apk_icon)

        apk_col = QVBoxLayout()
        apk_col.setSpacing(2)
        apk_title = QLabel("Imported APK Storage & Cache")
        apk_title.setStyleSheet("font-weight: 600; font-size: 12px; color: #ffffff;")
        self._apk_info_lbl = QLabel("Calculating...")
        self._apk_info_lbl.setStyleSheet("color: #8b8e94; font-size: 11px;")
        apk_col.addWidget(apk_title)
        apk_col.addWidget(self._apk_info_lbl)
        apk_row.addLayout(apk_col, 1)

        clear_cache_btn = QPushButton("Clear APK Cache")
        clear_cache_btn.setStyleSheet("padding: 4px 12px; font-size: 11px;")
        clear_cache_btn.clicked.connect(self._on_clear_apk_cache)
        apk_row.addWidget(clear_cache_btn)
        grid_layout.addLayout(apk_row)

        body.addWidget(grid_frame)

        # Folder Open Actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        open_appdata_btn = QPushButton("Open AppData Folder")
        open_appdata_btn.setIcon(get_icon("folder-open", size=13, color=TEXT_MUTED))
        open_appdata_btn.setIconSize(QSize(13, 13))
        open_appdata_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #212226;
                border: 1px solid #35373e;
                border-radius: 4px;
                color: #e5e7eb;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2a2c31;
            }
            """
        )
        open_appdata_btn.clicked.connect(self._on_open_appdata)
        btn_row.addWidget(open_appdata_btn)

        open_output_btn = QPushButton("Open Output Directory")
        open_output_btn.setIcon(get_icon("external-link", size=13, color=TEXT_MUTED))
        open_output_btn.setIconSize(QSize(13, 13))
        open_output_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #212226;
                border: 1px solid #35373e;
                border-radius: 4px;
                color: #e5e7eb;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2a2c31;
            }
            """
        )
        open_output_btn.clicked.connect(self._on_open_output_dir)
        btn_row.addWidget(open_output_btn)

        btn_row.addStretch(1)
        body.addLayout(btn_row)

        return card

    def _refresh_storage_stats(self) -> None:
        # DB Stats
        db_path = self._ctx.settings.database_path
        db_size = db_path.stat().st_size if db_path.is_file() else 0
        wal_path = db_path.with_suffix(".db-wal")
        if wal_path.is_file():
            db_size += wal_path.stat().st_size

        self._db_info_lbl.setText(
            f"Path: {db_path} · Current Size: {_format_size(db_size)}"
        )

        # APK Cache Stats
        apk_dir = self._ctx.settings.data_dir / "apks"
        apk_count = 0
        apk_total_size = 0
        if apk_dir.is_dir():
            for f in apk_dir.iterdir():
                if f.is_file():
                    apk_count += 1
                    apk_total_size += f.stat().st_size

        self._apk_info_lbl.setText(
            f"Path: {apk_dir} · {apk_count} cached package(s) ({_format_size(apk_total_size)})"
        )

    def _on_vacuum_db(self) -> None:
        try:
            self._ctx.repository.vacuum()
            self._refresh_storage_stats()
            QMessageBox.information(
                self,
                "Database Maintenance",
                "SQLite VACUUM completed successfully. Unused disk space reclaimed.",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Vacuum Error",
                f"Failed to vacuum SQLite database:\n{exc}",
            )

    def _on_clear_apk_cache(self) -> None:
        apk_dir = self._ctx.settings.data_dir / "apks"
        if not apk_dir.is_dir():
            return

        confirm = QMessageBox.question(
            self,
            "Clear APK Cache",
            "Are you sure you want to remove all cached APK files?\n"
            "This will not delete test history or findings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        removed = 0
        freed = 0
        for f in apk_dir.iterdir():
            if f.is_file():
                try:
                    size = f.stat().st_size
                    f.unlink()
                    removed += 1
                    freed += size
                except Exception:
                    pass

        self._refresh_storage_stats()
        QMessageBox.information(
            self,
            "Cache Cleared",
            f"Removed {removed} file(s), reclaiming {_format_size(freed)}.",
        )

    def _on_open_appdata(self) -> None:
        folder = self._ctx.settings.data_dir
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    def _on_open_output_dir(self) -> None:
        folder = self._ctx.settings.reports_output_dir or (self._ctx.settings.data_dir / "reports")
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    # -- 4. About & Statement of Limitations Card -----------------------------

    def _build_about_card(self) -> Card:
        card = Card("About & Legal")
        body = card.body_layout()

        # Version Info Block
        ver_box = QFrame()
        ver_box.setStyleSheet(
            f"background-color: #1e1f23; border: 1px solid {BORDER_LIGHT}; "
            "border-radius: 6px; padding: 10px;"
        )
        ver_layout = QHBoxLayout(ver_box)
        ver_layout.setContentsMargins(10, 8, 10, 8)

        app_ver = QLabel("<b>DroidDesk</b> v0.1.0")
        app_ver.setStyleSheet("font-size: 13px; color: #ffffff;")
        ver_layout.addWidget(app_ver)

        ver_layout.addSpacing(20)

        py_ver = sys.version.split()[0]
        qt_ver = qVersion()
        runtime_info = QLabel(
            f"Python {py_ver} · PySide6 {PySide6.__version__} · Qt {qt_ver} · {sys.platform}"
        )
        runtime_info.setStyleSheet("color: #8b8e94; font-size: 11px;")
        ver_layout.addWidget(runtime_info)
        ver_layout.addStretch(1)
        body.addWidget(ver_box)

        # Mandatory Statement of Limitations (§12.1)
        legal_frame = QFrame()
        legal_frame.setStyleSheet(
            "background-color: #211c1d; border: 1px solid #4a2226; "
            "border-radius: 6px; padding: 12px;"
        )
        legal_layout = QVBoxLayout(legal_frame)
        legal_layout.setContentsMargins(12, 10, 12, 10)
        legal_layout.setSpacing(6)

        legal_title = QLabel("Statement of Limitations (§12.1)")
        legal_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #e0574a;")
        legal_layout.addWidget(legal_title)

        legal_text = QLabel(_STATEMENT_OF_LIMITATIONS)
        legal_text.setWordWrap(True)
        legal_text.setStyleSheet("color: #d1d5db; font-size: 11px; line-height: 1.4;")
        legal_layout.addWidget(legal_text)

        body.addWidget(legal_frame)

        return card
