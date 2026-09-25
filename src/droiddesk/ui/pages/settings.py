"""Settings page: Developer toolchain discovery, executable overrides, and diagnostics.

Provides dynamic verification and custom path overrides for required Android SDK
and CLI tools, along with concise explanations of how each tool works and its purpose.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.ui.dialogs.setup_dialog import SetupDialog
from droiddesk.ui.theme import BORDER, BORDER_LIGHT, get_icon
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.status_pill import StatusPill

_TOOL_INFO: dict[str, tuple[str, str]] = {
    "adb": (
        "Android Debug Bridge",
        "Communicates with connected Android devices and emulators over USB/Wi-Fi to execute shell commands, capture live logcat streams, and install APKs.",
    ),
    "aapt2": (
        "Android Asset Packaging Tool",
        "Parses AndroidManifest.xml, inspects package identifiers and permissions, and extracts application icons and badge resources.",
    ),
    "apksigner": (
        "APK Signature Verifier",
        "Verifies APK cryptographic signing schemes (v1, v2, v3, v4), checks signing certificate validity, and confirms package integrity.",
    ),
    "apkanalyzer": (
        "APK Composition Analyzer",
        "Breaks down APK file composition, counts DEX bytecode methods, and analyzes application architecture overhead.",
    ),
    "bundletool": (
        "App Bundle Tool",
        "Inspects Android App Bundles (.aab), converts bundles into device-specific APK sets, and validates bundle configurations.",
    ),
    "gitleaks": (
        "Static Secret Scanner",
        "Scans project files and git repository commits to detect accidentally committed API keys, tokens, and hardcoded credentials.",
    ),
    "scrcpy": (
        "Device Screen Mirror",
        "Streams low-latency, real-time video display of connected Android devices and provides remote touch control over USB or Wi-Fi.",
    ),
    "git": (
        "Version Control Client",
        "Tracks repository changes, branch differences, and commit history used for automated secret leak scanning and file auditing.",
    ),
}


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
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        layout.addWidget(
            PageHeader(
                "Settings",
                "Verify and configure developer tools powering Android device control, APK analysis, and security scanning.",
            )
        )

        # Single unified Card containing toolbar, explanation, and table
        layout.addWidget(self._build_toolchain_card())

        layout.addStretch(1)
        scroll.setWidget(container)
        page_layout.addWidget(scroll)

        # Initial tool discovery
        self._refresh_tools()

    def _build_toolchain_card(self) -> Card:
        card = Card()
        body = card.body_layout()
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(10)

        # Action toolbar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)

        verify_btn = QPushButton("Verify All Tools")
        verify_btn.setIcon(get_icon("refresh-cw", size=13, color="#60a5fa"))
        verify_btn.setIconSize(QSize(13, 13))
        verify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        verify_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #1e293b;
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
        wizard_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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

        action_bar.addSpacing(10)

        self._tool_status_feedback = QLabel("")
        self._tool_status_feedback.setStyleSheet("color: #8b8e94; font-size: 11px;")
        action_bar.addWidget(self._tool_status_feedback)
        action_bar.addStretch(1)

        body.addLayout(action_bar)

        # Overview explanation banner
        info_bar = QFrame()
        info_bar.setObjectName("infoBanner")
        info_bar.setStyleSheet(
            f"""
            QFrame#infoBanner {{
                background-color: #191b20;
                border: 1px solid {BORDER_LIGHT};
                border-radius: 5px;
            }}
            """
        )
        info_layout = QHBoxLayout(info_bar)
        info_layout.setContentsMargins(12, 7, 12, 7)
        info_layout.setSpacing(8)

        info_icon = QLabel()
        info_icon.setPixmap(get_icon("info", size=14, color="#60a5fa").pixmap(14, 14))
        info_layout.addWidget(info_icon)

        info_text = QLabel(
            "<b>How it works & Purpose:</b> DroidDesk auto-detects required developer tools from your system "
            "<code>PATH</code>, Android SDK (<code>ANDROID_HOME</code>), and bundled binaries to power device control, "
            "APK analysis, and security scanning. Click <b>Browse...</b> to configure a custom path for any binary."
        )
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color: #9ca3af; font-size: 11px; line-height: 1.3;")
        info_layout.addWidget(info_text, 1)

        body.addWidget(info_bar)

        # Tool status table
        self._tool_table = QTableWidget(0, 5)
        self._tool_table.setHorizontalHeaderLabels(
            ["Tool", "Status", "Version", "Path", "Actions"]
        )
        tbl_hdr = self._tool_table.horizontalHeader()
        tbl_hdr.setStretchLastSection(False)
        tbl_hdr.setDefaultSectionSize(100)
        tbl_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        tbl_hdr.resizeSection(0, 110)
        tbl_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        tbl_hdr.resizeSection(1, 95)
        tbl_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        tbl_hdr.resizeSection(2, 175)
        tbl_hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        tbl_hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        tbl_hdr.resizeSection(4, 95)

        self._tool_table.verticalHeader().setVisible(False)
        self._tool_table.setShowGrid(False)
        self._tool_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tool_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tool_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tool_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tool_table.setFixedHeight(315)
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
                padding: 7px 10px;
            }
            QTableWidget::item:selected {
                background-color: #262930;
            }
            """
        )
        self._tool_table.cellClicked.connect(self._on_cell_clicked)
        body.addWidget(self._tool_table)

        # Interactive tool explanation footer
        detail_bar = QFrame()
        detail_bar.setObjectName("detailBar")
        detail_bar.setStyleSheet(
            f"""
            QFrame#detailBar {{
                background-color: #191a1e;
                border: 1px solid {BORDER};
                border-radius: 5px;
            }}
            """
        )
        detail_layout = QHBoxLayout(detail_bar)
        detail_layout.setContentsMargins(12, 7, 12, 7)
        detail_layout.setSpacing(8)

        detail_icon = QLabel()
        detail_icon.setPixmap(get_icon("help-circle", size=14, color="#27ae60").pixmap(14, 14))
        detail_layout.addWidget(detail_icon)

        self._tool_detail_lbl = QLabel(
            "💡 <b>Tip:</b> Click any tool row above to see what it does and how DroidDesk uses it."
        )
        self._tool_detail_lbl.setWordWrap(True)
        self._tool_detail_lbl.setStyleSheet("color: #d1d5db; font-size: 11px;")
        detail_layout.addWidget(self._tool_detail_lbl, 1)

        body.addWidget(detail_bar)

        return card

    def _on_cell_clicked(self, row: int, _col: int) -> None:
        tool_item = self._tool_table.item(row, 0)
        if tool_item:
            name = tool_item.text()
            if name in _TOOL_INFO:
                title, desc = _TOOL_INFO[name]
                self._tool_detail_lbl.setText(
                    f"<b>{name}</b> <span style='color:#8b8e94;'>({title}):</span> {desc}"
                )

    def _on_verify_all_tools(self) -> None:
        self._notify_services_and_refresh()
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._tool_status_feedback.setText(f"All tools verified actively at {now}.")

    def _on_run_setup_wizard(self) -> None:
        dlg = SetupDialog(self._ctx.settings, self._ctx.tool_locator, parent=self)
        if dlg.exec():
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
            self._tool_table.setRowHeight(row_idx, 35)

            # Tool name
            name_item = QTableWidgetItem(name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if name in _TOOL_INFO:
                t_title, t_desc = _TOOL_INFO[name]
                name_item.setToolTip(f"{name} ({t_title})\n{t_desc}")
            self._tool_table.setItem(row_idx, 0, name_item)

            # Status indicator
            pill_widget = QWidget()
            pill_layout = QHBoxLayout(pill_widget)
            pill_layout.setContentsMargins(6, 3, 6, 3)
            pill_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

            if info.is_bundled:
                pill = StatusPill("BUNDLED", "info")
            elif info.is_valid:
                pill = StatusPill("FOUND", "pass")
            else:
                pill = StatusPill("MISSING", "fail")

            pill_layout.addWidget(pill)
            self._tool_table.setCellWidget(row_idx, 1, pill_widget)

            # Version info
            ver_text = info.version or "-"
            if not info.is_valid and info.error_message and "Java runtime" in info.error_message:
                ver_text = "Java Required"
            ver_item = QTableWidgetItem(ver_text)
            ver_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            ver_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if not info.is_valid and info.error_message and "Java runtime" in info.error_message:
                ver_item.setToolTip(info.error_message)
            self._tool_table.setItem(row_idx, 2, ver_item)

            # Executable path
            path_str = str(info.path) if info.path else "(not found)"
            path_item = QTableWidgetItem(path_str)
            path_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            path_item.setToolTip(path_str)
            path_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            if not info.path:
                path_item.setForeground(Qt.GlobalColor.darkGray)
            self._tool_table.setItem(row_idx, 3, path_item)

            # Row actions
            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            browse_btn = QPushButton("Browse...")
            browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            browse_btn.setStyleSheet(
                "padding: 2px 10px; font-size: 11px; background-color: #212226; "
                "border: 1px solid #35373e; border-radius: 3px; color: #e5e7eb;"
            )
            browse_btn.clicked.connect(lambda _=None, t=name: self._on_override_tool(t))
            act_layout.addWidget(browse_btn)

            has_override = getattr(self._ctx.settings, f"{name}_path", None) is not None
            if has_override:
                reset_btn = QPushButton("Reset")
                reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                reset_btn.setStyleSheet(
                    "padding: 2px 10px; font-size: 11px; background-color: #2a1418; "
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
