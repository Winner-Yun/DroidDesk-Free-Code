"""Settings page: Device & APK history, theme configuration, and application info.

Provides device and APK history management with individual/bulk deletion,
light/dark mode toggling, application developer details, and contributor recognition.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
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
from droiddesk.ui.theme import apply_theme, get_icon
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.status_pill import StatusPill


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.setProperty("role", "page")

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 16, 24, 24)
        layout.setSpacing(16)

        layout.addWidget(
            PageHeader(
                "Settings & Preferences",
                "Configure display theme, manage device & APK history, and view application information.",
            )
        )

        # 1. Appearance & Theme Card (Light / Dark mode)
        layout.addWidget(self._build_theme_card())

        # 2. Android Environment & Toolchain Card
        layout.addWidget(self._build_android_env_card())

        # 3. Device History Card
        layout.addWidget(self._build_device_history_card())

        # 3. APK History Card
        layout.addWidget(self._build_apk_history_card())

        # 4. Application Information Card
        layout.addWidget(self._build_about_card())

        # 5. Bottom Sheet / Contributor note
        layout.addWidget(self._build_bottom_sheet_note())

        layout.addStretch(1)
        scroll.setWidget(container)
        page_layout.addWidget(scroll)

        # Initial dynamic data load
        self._refresh_device_history()
        self._refresh_apk_history()

    # -------------------------------------------------------------------------
    # Appearance & Theme Card
    # -------------------------------------------------------------------------
    def _build_theme_card(self) -> Card:
        card = Card()
        body = card.body_layout()
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(12)

        header_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("sun-moon", size=18, color="#3b82f6").pixmap(18, 18))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("Appearance & Theme")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        header_row.addWidget(title_lbl)

        self._theme_pill = StatusPill(
            f"{self._ctx.settings.theme_mode.upper()} MODE",
            "info" if self._ctx.settings.theme_mode == "dark" else "warn",
        )
        header_row.addWidget(self._theme_pill)
        header_row.addStretch(1)
        body.addLayout(header_row)

        desc_lbl = QLabel(
            "Configure your UI display theme preference. Changes apply instantly across the entire application and persist on restart."
        )
        desc_lbl.setStyleSheet("font-size: 12px; color: #6b7280;")
        body.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._dark_btn = QPushButton("Dark Mode")
        self._dark_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dark_btn.setIconSize(QSize(15, 15))
        self._dark_btn.clicked.connect(lambda: self._set_theme("dark"))

        self._light_btn = QPushButton("Light Mode")
        self._light_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._light_btn.setIconSize(QSize(15, 15))
        self._light_btn.clicked.connect(lambda: self._set_theme("light"))

        self._update_theme_buttons_style()

        btn_row.addWidget(self._dark_btn)
        btn_row.addWidget(self._light_btn)
        btn_row.addStretch(1)
        body.addLayout(btn_row)

        return card

    def _update_theme_buttons_style(self) -> None:
        active = self._ctx.settings.theme_mode.lower()
        is_dark = active == "dark"

        if is_dark:
            self._dark_btn.setIcon(get_icon("moon", size=15, color="#ffffff"))
            self._dark_btn.setStyleSheet(
                "QPushButton {"
                "   background-color: #1d4ed8; border: 2px solid #3b82f6; border-radius: 6px; "
                "   color: #ffffff; font-weight: 700; padding: 8px 20px; font-size: 12px;"
                "}"
            )
            self._light_btn.setIcon(get_icon("sun", size=15, color="#8b8e94"))
            self._light_btn.setStyleSheet(
                "QPushButton {"
                "   background-color: #212226; border: 1px solid #35373e; border-radius: 6px; "
                "   color: #9ca3af; font-weight: 500; padding: 8px 20px; font-size: 12px;"
                "}"
                "QPushButton:hover {"
                "   background-color: #2a2c31; color: #ffffff;"
                "}"
            )
            self._theme_pill.set_status("DARK MODE", "info")
        else:
            self._light_btn.setIcon(get_icon("sun", size=15, color="#ffffff"))
            self._light_btn.setStyleSheet(
                "QPushButton {"
                "   background-color: #2563eb; border: 2px solid #3b82f6; border-radius: 6px; "
                "   color: #ffffff; font-weight: 700; padding: 8px 20px; font-size: 12px;"
                "}"
            )
            self._dark_btn.setIcon(get_icon("moon", size=15, color="#6b7280"))
            self._dark_btn.setStyleSheet(
                "QPushButton {"
                "   background-color: #ffffff; border: 1px solid #d1d5db; border-radius: 6px; "
                "   color: #374151; font-weight: 500; padding: 8px 20px; font-size: 12px;"
                "}"
                "QPushButton:hover {"
                "   background-color: #f3f4f6; color: #111827;"
                "}"
            )
            self._theme_pill.set_status("LIGHT MODE", "warn")

    def _set_theme(self, mode: str) -> None:
        if self._ctx.settings.theme_mode == mode:
            return
        self._ctx.settings.theme_mode = mode
        self._ctx.settings.save()
        apply_theme(mode, widget=self)
        self._update_theme_buttons_style()

    # -------------------------------------------------------------------------
    # Android SDK & Environment Card
    # -------------------------------------------------------------------------
    def _build_android_env_card(self) -> Card:
        card = Card()
        body = card.body_layout()
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(12)

        header_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("settings", size=18, color="#3b82f6").pixmap(18, 18))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("Android SDK & Environment")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        header_row.addWidget(title_lbl)

        self._env_pill = StatusPill("CHECKING", "info")
        header_row.addWidget(self._env_pill)
        header_row.addStretch(1)
        body.addLayout(header_row)

        desc_lbl = QLabel(
            "Manage your Android SDK installation, view tool availability (ADB, Emulator, AVD Manager), and inspect installed system images."
        )
        desc_lbl.setStyleSheet("font-size: 12px; color: #6b7280;")
        body.addWidget(desc_lbl)

        # SDK Path row
        path_box = QFrame()
        path_box.setStyleSheet("background-color: #212226; border-radius: 6px; padding: 10px;")
        pb_layout = QVBoxLayout(path_box)
        pb_layout.setContentsMargins(8, 6, 8, 6)
        pb_layout.setSpacing(6)

        p_lbl = QLabel("Android SDK Root Location:")
        p_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #9ca3af;")
        pb_layout.addWidget(p_lbl)

        p_row = QHBoxLayout()
        self._sdk_path_input = QLineEdit()
        p_row.addWidget(self._sdk_path_input, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_sdk_path)
        p_row.addWidget(browse_btn)

        save_btn = QPushButton("Save & Revalidate")
        save_btn.setStyleSheet(
            "QPushButton { background: #2563eb; border: 1px solid #3b82f6; color: #ffffff; "
            "border-radius: 4px; padding: 6px 14px; font-weight: 600; font-size: 11px; }"
            "QPushButton:hover { background: #1d4ed8; }"
        )
        save_btn.clicked.connect(self._save_sdk_path)
        p_row.addWidget(save_btn)
        pb_layout.addLayout(p_row)
        body.addWidget(path_box)

        # Tools summary grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)

        # SDK Status
        grid.addWidget(self._env_field_label("SDK Root:"), 0, 0)
        self._sdk_status_val = QLabel("-")
        grid.addWidget(self._sdk_status_val, 0, 1)

        # ADB Status
        grid.addWidget(self._env_field_label("ADB:"), 1, 0)
        self._adb_status_val = QLabel("-")
        grid.addWidget(self._adb_status_val, 1, 1)

        # Emulator Status
        grid.addWidget(self._env_field_label("Emulator:"), 2, 0)
        self._emu_status_val = QLabel("-")
        grid.addWidget(self._emu_status_val, 2, 1)

        # System Images
        grid.addWidget(self._env_field_label("System Images:"), 3, 0)
        self._si_status_val = QLabel("-")
        grid.addWidget(self._si_status_val, 3, 1)

        # Storage / Emulator location
        grid.addWidget(self._env_field_label("Emulator Storage:"), 4, 0)
        self._avd_loc_val = QLabel(str(Path.home() / ".android" / "avd"))
        self._avd_loc_val.setStyleSheet("font-family: monospace; font-size: 11px; color: #9ca3af;")
        grid.addWidget(self._avd_loc_val, 4, 1)

        body.addLayout(grid)
        self._refresh_android_env_info()
        return card

    def _env_field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #9ca3af;")
        lbl.setFixedWidth(130)
        return lbl

    def _browse_sdk_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Android SDK Directory",
            self._sdk_path_input.text().strip() or str(Path.home()),
        )
        if folder:
            self._sdk_path_input.setText(folder)

    def _save_sdk_path(self) -> None:
        raw = self._sdk_path_input.text().strip()
        if not raw:
            return
        p = Path(raw)
        if not p.is_dir():
            QMessageBox.warning(self, "Invalid Path", f"Directory does not exist:\n{raw}")
            return
        try:
            self._ctx.device_service.sdk_manager.set_sdk_path(p)
            QMessageBox.information(self, "SDK Path Saved", "Android SDK location updated successfully.")
            self._refresh_android_env_info()
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Could not update SDK path: {exc}")

    def _refresh_android_env_info(self) -> None:
        status = self._ctx.device_service.check_environment()
        if status.sdk_root:
            self._sdk_path_input.setText(str(status.sdk_root))
            self._sdk_status_val.setText(f"Ready ({status.sdk_root})")
            self._sdk_status_val.setStyleSheet("color: #10b981; font-weight: 600; font-size: 12px;")
        else:
            self._sdk_status_val.setText("Not Found")
            self._sdk_status_val.setStyleSheet("color: #ef4444; font-weight: 600; font-size: 12px;")

        if status.adb_path:
            self._adb_status_val.setText(f"Ready ({status.adb_version or status.adb_path.name})")
            self._adb_status_val.setStyleSheet("color: #10b981; font-weight: 600; font-size: 12px;")
        else:
            self._adb_status_val.setText("Missing")
            self._adb_status_val.setStyleSheet("color: #ef4444; font-weight: 600; font-size: 12px;")

        if status.emulator_path:
            self._emu_status_val.setText(f"Ready ({status.emulator_version or status.emulator_path.name})")
            self._emu_status_val.setStyleSheet("color: #10b981; font-weight: 600; font-size: 12px;")
        else:
            self._emu_status_val.setText("Missing")
            self._emu_status_val.setStyleSheet("color: #ef4444; font-weight: 600; font-size: 12px;")

        from droiddesk.android.system_image_manager import SystemImageManager
        sim = SystemImageManager(self._ctx.tool_locator)
        imgs = sim.list_installed_images()
        if imgs:
            versions = ", ".join(f"API {img.api_level}" for img in imgs)
            self._si_status_val.setText(f"{len(imgs)} installed ({versions})")
            self._si_status_val.setStyleSheet("color: #10b981; font-size: 12px;")
        else:
            self._si_status_val.setText("None installed (Download via + Create Emulator)")
            self._si_status_val.setStyleSheet("color: #fbbf24; font-size: 12px;")

        if status.is_ready:
            self._env_pill.set_status("READY", "pass")
        elif "MISSING" in status.state.value:
            self._env_pill.set_status(status.state.value.replace("_", " "), "fail")
        else:
            self._env_pill.set_status(status.state.value.replace("_", " "), "warn")

    # -------------------------------------------------------------------------
    # Device Connection History Card
    # -------------------------------------------------------------------------
    def _build_device_history_card(self) -> Card:
        card = Card()
        body = card.body_layout()
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        title_icon = QLabel()
        title_icon.setPixmap(get_icon("smartphone", size=18, color="#3b82f6").pixmap(18, 18))
        toolbar.addWidget(title_icon)

        title_lbl = QLabel("Device Connection History")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        toolbar.addWidget(title_lbl)

        self._device_count_lbl = QLabel("")
        self._device_count_lbl.setStyleSheet("color: #8b8e94; font-size: 11px;")
        toolbar.addWidget(self._device_count_lbl)
        toolbar.addStretch(1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(get_icon("refresh-cw", size=12, color="#9ca3af"))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_device_history)
        toolbar.addWidget(refresh_btn)

        clear_all_btn = QPushButton("Clear All Devices")
        clear_all_btn.setIcon(get_icon("trash-2", size=12, color="#ef4444"))
        clear_all_btn.setProperty("role", "danger")
        clear_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_all_btn.clicked.connect(self._on_clear_all_devices)
        toolbar.addWidget(clear_all_btn)

        body.addLayout(toolbar)

        self._device_table = QTableWidget(0, 8)
        self._device_table.setHorizontalHeaderLabels(
            ["Model / Device", "Serial Number", "State", "Android", "API", "ABI", "Last Connected", "Action"]
        )
        d_hdr = self._device_table.horizontalHeader()
        d_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        d_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        d_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        d_hdr.resizeSection(2, 80)
        d_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        d_hdr.resizeSection(3, 75)
        d_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        d_hdr.resizeSection(4, 55)
        d_hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        d_hdr.resizeSection(5, 75)
        d_hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        d_hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        d_hdr.resizeSection(7, 85)

        self._device_table.verticalHeader().setVisible(False)
        self._device_table.setShowGrid(False)
        self._device_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._device_table.setFixedHeight(220)
        body.addWidget(self._device_table)

        return card

    def _refresh_device_history(self) -> None:
        records = self._ctx.repository.list_device_history()
        self._device_count_lbl.setText(f"({len(records)} devices recorded)")
        self._device_table.setRowCount(len(records))

        for row_idx, dev in enumerate(records):
            self._device_table.setRowHeight(row_idx, 38)

            m_item = QTableWidgetItem(str(dev["model"]))
            m_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._device_table.setItem(row_idx, 0, m_item)

            serial_str = str(dev["serial"])
            s_item = QTableWidgetItem(serial_str)
            s_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._device_table.setItem(row_idx, 1, s_item)

            state_widget = QWidget()
            s_layout = QHBoxLayout(state_widget)
            s_layout.setContentsMargins(4, 2, 4, 2)
            s_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            state_str = str(dev["state"])
            pill = StatusPill(state_str.upper(), "pass" if state_str == "device" else "warn")
            s_layout.addWidget(pill)
            self._device_table.setCellWidget(row_idx, 2, state_widget)

            ver_item = QTableWidgetItem(str(dev["android_version"]))
            ver_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._device_table.setItem(row_idx, 3, ver_item)

            api_item = QTableWidgetItem(str(dev["api_level"]))
            api_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._device_table.setItem(row_idx, 4, api_item)

            abi_item = QTableWidgetItem(str(dev["abi"]))
            abi_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._device_table.setItem(row_idx, 5, abi_item)

            conn_item = QTableWidgetItem(str(dev["last_connected"]))
            conn_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._device_table.setItem(row_idx, 6, conn_item)

            act_widget = QWidget()
            a_layout = QHBoxLayout(act_widget)
            a_layout.setContentsMargins(2, 2, 2, 2)
            del_btn = QPushButton("Remove")
            del_btn.setProperty("role", "tableActionDanger")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.clicked.connect(lambda _=None, s=serial_str: self._on_remove_device(s))
            a_layout.addWidget(del_btn)
            self._device_table.setCellWidget(row_idx, 7, act_widget)

    def _on_remove_device(self, serial: str) -> None:
        self._ctx.repository.delete_device_history(serial)
        self._refresh_device_history()

    def _on_clear_all_devices(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear Device History",
            "Are you sure you want to remove all historically recorded devices?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._ctx.repository.clear_device_history()
            self._refresh_device_history()

    # -------------------------------------------------------------------------
    # APK Inspection History Card
    # -------------------------------------------------------------------------
    def _build_apk_history_card(self) -> Card:
        card = Card()
        body = card.body_layout()
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        title_icon = QLabel()
        title_icon.setPixmap(get_icon("box", size=18, color="#10b981").pixmap(18, 18))
        toolbar.addWidget(title_icon)

        title_lbl = QLabel("APK Inspection History")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        toolbar.addWidget(title_lbl)

        self._apk_count_lbl = QLabel("")
        self._apk_count_lbl.setStyleSheet("color: #8b8e94; font-size: 11px;")
        toolbar.addWidget(self._apk_count_lbl)
        toolbar.addStretch(1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setIcon(get_icon("refresh-cw", size=12, color="#9ca3af"))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_apk_history)
        toolbar.addWidget(refresh_btn)

        clear_all_btn = QPushButton("Clear All APKs")
        clear_all_btn.setIcon(get_icon("trash-2", size=12, color="#ef4444"))
        clear_all_btn.setProperty("role", "danger")
        clear_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_all_btn.clicked.connect(self._on_clear_all_apks)
        toolbar.addWidget(clear_all_btn)

        body.addLayout(toolbar)

        self._apk_table = QTableWidget(0, 7)
        self._apk_table.setHorizontalHeaderLabels(
            ["Package Name", "File Name", "Version", "Target SDK", "Size", "Analyzed At", "Action"]
        )
        a_hdr = self._apk_table.horizontalHeader()
        a_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        a_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        a_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        a_hdr.resizeSection(2, 85)
        a_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        a_hdr.resizeSection(3, 85)
        a_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        a_hdr.resizeSection(4, 75)
        a_hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        a_hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        a_hdr.resizeSection(6, 85)

        self._apk_table.verticalHeader().setVisible(False)
        self._apk_table.setShowGrid(False)
        self._apk_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._apk_table.setFixedHeight(220)
        body.addWidget(self._apk_table)

        return card

    def _refresh_apk_history(self) -> None:
        apks = self._ctx.repository.list_apks()
        self._apk_count_lbl.setText(f"({len(apks)} APKs recorded)")
        self._apk_table.setRowCount(len(apks))

        for row_idx, apk in enumerate(apks):
            self._apk_table.setRowHeight(row_idx, 38)

            pkg_item = QTableWidgetItem(apk.package_name)
            pkg_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._apk_table.setItem(row_idx, 0, pkg_item)

            fn_item = QTableWidgetItem(apk.file_path.name if apk.file_path else "-")
            fn_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._apk_table.setItem(row_idx, 1, fn_item)

            v_str = f"{apk.version_name or '-'} ({apk.version_code or '-'})"
            v_item = QTableWidgetItem(v_str)
            v_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._apk_table.setItem(row_idx, 2, v_item)

            sdk_str = f"API {apk.target_sdk}" if apk.target_sdk else "-"
            sdk_item = QTableWidgetItem(sdk_str)
            sdk_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._apk_table.setItem(row_idx, 3, sdk_item)

            size_str = _format_size(apk.size_bytes)
            size_item = QTableWidgetItem(size_str)
            size_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._apk_table.setItem(row_idx, 4, size_item)

            time_str = apk.analyzed_at.strftime("%Y-%m-%d %H:%M:%S") if apk.analyzed_at else "-"
            t_item = QTableWidgetItem(time_str)
            t_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._apk_table.setItem(row_idx, 5, t_item)

            act_widget = QWidget()
            a_layout = QHBoxLayout(act_widget)
            a_layout.setContentsMargins(2, 2, 2, 2)
            del_btn = QPushButton("Remove")
            del_btn.setProperty("role", "tableActionDanger")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            f_hash = apk.file_hash
            del_btn.clicked.connect(lambda _=None, h=f_hash: self._on_remove_apk(h))
            a_layout.addWidget(del_btn)
            self._apk_table.setCellWidget(row_idx, 6, act_widget)

    def _on_remove_apk(self, file_hash: str) -> None:
        self._ctx.repository.delete_apk(file_hash)
        if self._ctx.settings.active_apk_hash == file_hash:
            self._ctx.settings.active_apk_hash = None
            self._ctx.settings.save()
        self._refresh_apk_history()

    def _on_clear_all_apks(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear APK History",
            "Are you sure you want to remove all APK history and their associated test records?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._ctx.repository.clear_apks()
            self._ctx.settings.active_apk_hash = None
            self._ctx.settings.save()
            self._refresh_apk_history()

    # -------------------------------------------------------------------------
    #  Application Information Card
    # -------------------------------------------------------------------------
    def _build_about_card(self) -> Card:
        card = Card()
        body = card.body_layout()
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(12)

        hdr_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("info", size=18, color="#3b82f6").pixmap(18, 18))
        hdr_row.addWidget(icon_lbl)

        title = QLabel("About DroidDesk")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        hdr_row.addWidget(title)
        hdr_row.addStretch(1)
        body.addLayout(hdr_row)

        desc_lbl = QLabel(
            "<b>DroidDesk</b> is a local Android development companion for Windows. "
            "It consolidates device control, APK inspection, automated testing, static secret scanning, "
            "and pre-release verification into a single desktop application without relying on external cloud services."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 12px; line-height: 1.4;")
        body.addWidget(desc_lbl)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)

        # Developer
        dev_label = QLabel("Developer:")
        dev_label.setProperty("role", "dim")
        dev_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        dev_val = QLabel("Winner Yun")
        dev_val.setStyleSheet("font-size: 12px; font-weight: 700; color: #3b82f6;")
        grid.addWidget(dev_label, 0, 0)
        grid.addWidget(dev_val, 0, 1)

        # Team
        team_label = QLabel("Team:")
        team_label.setProperty("role", "dim")
        team_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        team_val = QLabel("Khansha Team")
        team_val.setStyleSheet("font-size: 12px; font-weight: 700; color: #10b981;")
        grid.addWidget(team_label, 1, 0)
        grid.addWidget(team_val, 1, 1)

        # Date Created
        date_label = QLabel("Date Created:")
        date_label.setProperty("role", "dim")
        date_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        date_val = QLabel("30/9/2026")
        date_val.setStyleSheet("font-size: 12px; font-weight: 600;")
        grid.addWidget(date_label, 2, 0)
        grid.addWidget(date_val, 2, 1)

        # Repository Link
        repo_label = QLabel("Repository:")
        repo_label.setProperty("role", "dim")
        repo_label.setStyleSheet("font-size: 12px; font-weight: 600;")

        repo_layout = QHBoxLayout()
        repo_link = QLabel(
            '<a href="https://github.com/Winner-Yun" style="color: #3b82f6; text-decoration: underline;">'
            'https://github.com/Winner-Yun</a>'
        )
        repo_link.setOpenExternalLinks(True)
        repo_link.setStyleSheet("font-size: 12px;")
        repo_layout.addWidget(repo_link)
        repo_layout.addStretch(1)

        grid.addWidget(repo_label, 3, 0)
        grid.addLayout(repo_layout, 3, 1)

        body.addLayout(grid)
        return card

    # -------------------------------------------------------------------------
    #  Bottom Sheet / Contributor note
    # -------------------------------------------------------------------------
    def _build_bottom_sheet_note(self) -> QFrame:
        sheet = QFrame()
        sheet.setObjectName("bottomSheet")

        s_layout = QHBoxLayout(sheet)
        s_layout.setContentsMargins(14, 12, 14, 12)
        s_layout.setSpacing(12)

        from droiddesk.ui.theme import is_light

        avatar_color = "#0284c7" if is_light() else "#38bdf8"
        avatar_lbl = QLabel()
        avatar_lbl.setPixmap(get_icon("user-check", size=24, color=avatar_color).pixmap(24, 24))
        s_layout.addWidget(avatar_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        note_title = QLabel("Special Contributor Recognition")
        note_title.setObjectName("bottomSheetTitle")
        text_col.addWidget(note_title)

        note_content = QLabel(
            "<b>Leave Sovatnak</b> - He also work on the device functional."
        )
        note_content.setWordWrap(True)
        note_content.setStyleSheet("font-size: 12px; line-height: 1.3;")
        text_col.addWidget(note_content)

        s_layout.addLayout(text_col, 1)
        return sheet

    def set_device(self, device: object) -> None:
        self._active_device = device
