"""First-run setup & toolchain configuration dialog.

Provides Android SDK directory picking, live subfolder inspection (platform-tools,
build-tools, cmdline-tools), official download links, and discovery retry.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.config import Settings
from droiddesk.infra.tools import ToolLocator
from droiddesk.ui.theme import STATUS_COLORS, get_icon, get_pixmap


class SetupDialog(QDialog):
    """Setup dialog for configuring the Android SDK and external toolchain."""

    def __init__(
        self,
        settings: Settings,
        tool_locator: ToolLocator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tool_locator = tool_locator

        self.setWindowTitle("DroidDesk Setup - Android SDK & Toolchain")
        self.setMinimumWidth(560)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1a1b1e;
                color: #e5e7eb;
            }
            QLabel {
                color: #e5e7eb;
            }
            QLineEdit {
                background-color: #212226;
                color: #ffffff;
                border: 1px solid #35373e;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        # Header
        header_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_pixmap("wrench", size=24, color="#3b82f6"))
        header_row.addWidget(icon_lbl)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title_lbl = QLabel("Android SDK & Toolchain Setup")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        desc_lbl = QLabel(
            "DroidDesk requires the Android SDK Platform-Tools (primarily adb) to detect "
            "devices, install APKs, and execute automated test suites."
        )
        desc_lbl.setStyleSheet("color: #8b8e94; font-size: 12px;")
        desc_lbl.setWordWrap(True)
        title_block.addWidget(title_lbl)
        title_block.addWidget(desc_lbl)
        header_row.addLayout(title_block, 1)
        layout.addLayout(header_row)

        # Help / Download Callout Box
        help_box = QFrame()
        help_box.setStyleSheet(
            "background-color: #212226; border: 1px solid #2c2d33; "
            "border-radius: 6px; padding: 10px;"
        )
        help_layout = QVBoxLayout(help_box)
        help_layout.setContentsMargins(10, 8, 10, 8)
        help_layout.setSpacing(6)

        help_top = QHBoxLayout()
        help_text = QLabel(
            "Need the Android tools? If you have Android Studio installed, the SDK is typically "
            "at <b>%LOCALAPPDATA%\\Android\\Sdk</b>. Otherwise, download Platform-Tools standalone:"
        )
        help_text.setStyleSheet("color: #9ca3af; font-size: 11px;")
        help_text.setWordWrap(True)
        help_top.addWidget(help_text, 1)

        dl_btn = QPushButton("Download Platform-Tools")
        dl_btn.setIcon(get_icon("external-link", size=12, color="#3b82f6"))
        dl_btn.setIconSize(QSize(12, 12))
        dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dl_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2a2c31;
                border: 1px solid #3b82f6;
                color: #60a5fa;
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                color: #ffffff;
            }
            """
        )
        dl_btn.clicked.connect(self._open_platform_tools_download)
        help_top.addWidget(dl_btn)
        help_layout.addLayout(help_top)
        layout.addWidget(help_box)

        # SDK Folder Picker Section
        picker_label = QLabel("Android SDK Root Directory:")
        picker_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #d1d5db;")
        layout.addWidget(picker_label)

        picker_row = QHBoxLayout()
        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText(r"e.g. C:\Android\sdk or %LOCALAPPDATA%\Android\Sdk")

        init_path = ""
        if self._settings.android_sdk_path and self._settings.android_sdk_path.is_dir():
            init_path = str(self._settings.android_sdk_path)
        else:
            cand = self._find_default_sdk_candidate()
            if cand:
                init_path = str(cand)

        self._path_input.setText(init_path)
        self._path_input.textChanged.connect(self._inspect_sdk)
        picker_row.addWidget(self._path_input, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setIcon(get_icon("folder-open", size=13, color="#8b8e94"))
        browse_btn.setIconSize(QSize(13, 13))
        browse_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #212226;
                border: 1px solid #35373e;
                color: #e5e7eb;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2a2c31;
                border-color: #4b5563;
            }
            """
        )
        browse_btn.clicked.connect(self._browse_sdk_folder)
        picker_row.addWidget(browse_btn)
        layout.addLayout(picker_row)

        # Inspection Results Card
        inspect_card = QFrame()
        inspect_card.setStyleSheet(
            "background-color: #212226; border: 1px solid #2c2d33; "
            "border-radius: 6px; padding: 12px;"
        )
        inspect_layout = QVBoxLayout(inspect_card)
        inspect_layout.setContentsMargins(12, 10, 12, 10)
        inspect_layout.setSpacing(8)

        card_title = QLabel("Toolchain Components Inspection")
        card_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #9ca3af;")
        inspect_layout.addWidget(card_title)

        self._comp_labels: dict[str, tuple[QLabel, QLabel]] = {}
        components = [
            ("platform-tools", "Platform-Tools (adb.exe)"),
            ("build-tools", "Build-Tools (aapt2.exe, apksigner)"),
            ("cmdline-tools", "Command-line Tools (apkanalyzer)"),
            ("java", "Java Runtime (JBR / JDK)"),
        ]

        for key, title in components:
            row = QHBoxLayout()
            name_lbl = QLabel(title)
            name_lbl.setStyleSheet("font-size: 12px; font-weight: 500;")
            status_lbl = QLabel("Checking...")
            status_lbl.setStyleSheet("font-size: 11px; color: #8b8e94;")
            row.addWidget(name_lbl)
            row.addStretch(1)
            row.addWidget(status_lbl)
            inspect_layout.addLayout(row)
            self._comp_labels[key] = (name_lbl, status_lbl)

        layout.addWidget(inspect_card)

        # Bottom Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        retry_btn = QPushButton("Retry Discovery")
        retry_btn.setIcon(get_icon("refresh-cw", size=13, color="#8b8e94"))
        retry_btn.setIconSize(QSize(13, 13))
        retry_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #212226;
                border: 1px solid #35373e;
                color: #e5e7eb;
                border-radius: 4px;
                padding: 7px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2a2c31;
            }
            """
        )
        retry_btn.clicked.connect(self._retry_discovery)
        btn_row.addWidget(retry_btn)

        btn_row.addStretch(1)

        cancel_btn = QPushButton("Skip for now")
        cancel_btn.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: 1px solid #35373e;
                color: #8b8e94;
                border-radius: 4px;
                padding: 7px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #e5e7eb;
                background-color: #212226;
            }
            """
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._save_btn = QPushButton("Save & Continue")
        self._save_btn.setIcon(get_icon("check", size=13, color="#ffffff"))
        self._save_btn.setIconSize(QSize(13, 13))
        self._save_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2563eb;
                border: 1px solid #3b82f6;
                color: #ffffff;
                border-radius: 4px;
                padding: 7px 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            """
        )
        self._save_btn.clicked.connect(self._on_save_and_continue)
        btn_row.addWidget(self._save_btn)

        layout.addLayout(btn_row)

        self._inspect_sdk()

    def _open_platform_tools_download(self) -> None:
        QDesktopServices.openUrl(
            QUrl("https://developer.android.com/tools/releases/platform-tools")
        )

    def _browse_sdk_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Android SDK Directory",
            self._path_input.text().strip() or str(Path.home()),
        )
        if folder:
            self._path_input.setText(folder)

    def _find_default_sdk_candidate(self) -> Path | None:
        # Check env
        for env_key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            val = os.environ.get(env_key)
            if val and Path(val).is_dir():
                return Path(val)
        # Check LocalAppData
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            cand = Path(local_app_data) / "Android" / "Sdk"
            if cand.is_dir():
                return cand
        # Check standard C:\Android\sdk
        cand = Path(r"C:\Android\sdk")
        if cand.is_dir():
            return cand
        return None

    def _inspect_sdk(self) -> None:
        raw_path = self._path_input.text().strip()
        sdk_path = Path(raw_path) if raw_path else None
        valid_sdk_dir = sdk_path is not None and sdk_path.is_dir()

        pass_style = f"font-size: 11px; font-weight: 600; color: {STATUS_COLORS['pass']};"

        # Platform tools
        pt_lbl = self._comp_labels["platform-tools"][1]
        adb_found = False
        if valid_sdk_dir and sdk_path is not None:
            adb_cand = sdk_path / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
            if adb_cand.is_file():
                pt_lbl.setText("Found: platform-tools/adb.exe")
                pt_lbl.setStyleSheet(pass_style)
                adb_found = True
            else:
                pt_lbl.setText("Missing: platform-tools/adb.exe not found")
                pt_lbl.setStyleSheet(f"font-size: 11px; color: {STATUS_COLORS['fail']};")
        else:
            pt_lbl.setText("Specify a valid SDK directory")
            pt_lbl.setStyleSheet("font-size: 11px; color: #8b8e94;")

        # Build tools
        bt_lbl = self._comp_labels["build-tools"][1]
        if valid_sdk_dir and sdk_path is not None:
            bt_dir = sdk_path / "build-tools"
            if bt_dir.is_dir():
                versions = sorted([d.name for d in bt_dir.iterdir() if d.is_dir()], reverse=True)
                if versions:
                    bt_lbl.setText(f"Found: v{versions[0]} (aapt2, apksigner)")
                    bt_lbl.setStyleSheet(pass_style)
                else:
                    bt_lbl.setText("Missing: build-tools directory is empty")
                    bt_lbl.setStyleSheet(f"font-size: 11px; color: {STATUS_COLORS['warn']};")
            else:
                bt_lbl.setText("Missing: build-tools/ not found")
                bt_lbl.setStyleSheet(f"font-size: 11px; color: {STATUS_COLORS['warn']};")
        else:
            bt_lbl.setText("Waiting for SDK directory...")
            bt_lbl.setStyleSheet("font-size: 11px; color: #8b8e94;")

        # Cmdline tools
        cmd_lbl = self._comp_labels["cmdline-tools"][1]
        if valid_sdk_dir and sdk_path is not None:
            cmd_dir = sdk_path / "cmdline-tools"
            if cmd_dir.is_dir():
                found_cmdline = False
                for sub in cmd_dir.iterdir():
                    if (sub / "bin" / "apkanalyzer.bat").is_file() or (
                        sub / "bin" / "apkanalyzer"
                    ).is_file():
                        found_cmdline = True
                        break
                if found_cmdline:
                    cmd_lbl.setText("Found: cmdline-tools (apkanalyzer)")
                    cmd_lbl.setStyleSheet(pass_style)
                else:
                    cmd_lbl.setText("Optional: cmdline-tools/apkanalyzer not found")
                    cmd_lbl.setStyleSheet("font-size: 11px; color: #8b8e94;")
            else:
                cmd_lbl.setText("Optional: cmdline-tools/ not found")
                cmd_lbl.setStyleSheet("font-size: 11px; color: #8b8e94;")
        else:
            cmd_lbl.setText("Waiting for SDK directory...")
            cmd_lbl.setStyleSheet("font-size: 11px; color: #8b8e94;")

        # Java runtime
        java_lbl = self._comp_labels["java"][1]
        java_home = self._tool_locator.find_java_home()
        if java_home:
            java_lbl.setText(f"Found: {java_home.name}")
            java_lbl.setStyleSheet(pass_style)
        else:
            java_lbl.setText("Missing: Java runtime (needed for apksigner & apkanalyzer)")
            java_lbl.setStyleSheet(f"font-size: 11px; color: {STATUS_COLORS['warn']};")

        # Save button styling
        if adb_found:
            self._save_btn.setText("Save & Continue")
            self._save_btn.setEnabled(True)
        else:
            self._save_btn.setText("Save Paths Anyway")
            self._save_btn.setEnabled(True)

    def _retry_discovery(self) -> None:
        self._tool_locator.invalidate_cache()
        cand = self._find_default_sdk_candidate()
        if cand:
            self._path_input.setText(str(cand))
        self._inspect_sdk()

    def _on_save_and_continue(self) -> None:
        raw_path = self._path_input.text().strip()
        if raw_path:
            sdk_path = Path(raw_path)
            self._settings.android_sdk_path = sdk_path
            self._settings.save()
            self._tool_locator.invalidate_cache()

        self.accept()
