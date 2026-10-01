"""Android Environment Diagnostics & Configuration dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.android.models import AndroidEnvStatus
from droiddesk.android.sdk_manager import AndroidSdkManager
from droiddesk.android.system_image_manager import SystemImageManager
from droiddesk.ui.theme import get_icon


class AndroidEnvironmentDialog(QDialog):
    """Dialog displaying Android toolchain readiness and allowing SDK path customization."""

    def __init__(
        self,
        sdk_manager: AndroidSdkManager,
        system_image_manager: SystemImageManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sdk_mgr = sdk_manager
        self._sim_mgr = system_image_manager

        self.setWindowTitle("Android Environment & Toolchain Diagnostics")
        self.resize(650, 560)
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
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        h_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("settings", size=22, color="#3b82f6").pixmap(22, 22))
        h_row.addWidget(icon_lbl)
        title = QLabel("Android Development Environment")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        h_row.addWidget(title)
        h_row.addStretch(1)

        self._overall_badge = QLabel("READY")
        self._overall_badge.setStyleSheet(
            "background-color: #064e3b; color: #34d399; font-weight: 700; "
            "border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )
        h_row.addWidget(self._overall_badge)
        layout.addLayout(h_row)

        desc = QLabel(
            "DroidDesk integrates directly with the official Android SDK tools "
            "installed on your PC. Ensure the components below are detected and ready."
        )
        desc.setStyleSheet("font-size: 12px; color: #8b8e94;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # SDK Path Configuration Row
        path_box = QFrame()
        path_box.setStyleSheet("background-color: #212226; border-radius: 6px; padding: 10px;")
        pb_layout = QVBoxLayout(path_box)
        pb_layout.setContentsMargins(8, 6, 8, 6)
        pb_layout.setSpacing(6)

        p_lbl = QLabel("Android SDK Root Directory:")
        p_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #9ca3af;")
        pb_layout.addWidget(p_lbl)

        p_row = QHBoxLayout()
        self._path_input = QLineEdit()
        p_row.addWidget(self._path_input, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_sdk)
        p_row.addWidget(browse_btn)

        apply_btn = QPushButton("Save & Revalidate")
        apply_btn.setStyleSheet(
            "QPushButton { background: #2563eb; border: 1px solid #3b82f6; color: #ffffff; "
            "border-radius: 4px; padding: 6px 14px; font-weight: 600; }"
        )
        apply_btn.clicked.connect(self._apply_sdk_path)
        p_row.addWidget(apply_btn)
        pb_layout.addLayout(p_row)
        layout.addWidget(path_box)

        # Toolchain Status Table
        t_lbl = QLabel("Toolchain Components:")
        t_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #9ca3af;")
        layout.addWidget(t_lbl)

        self._tool_table = QTableWidget(0, 3)
        self._tool_table.setHorizontalHeaderLabels(["Component", "Status", "Version / Location"])
        thdr = self._tool_table.horizontalHeader()
        thdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        thdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        thdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._tool_table.verticalHeader().setVisible(False)
        self._tool_table.setShowGrid(False)
        self._tool_table.setFixedHeight(160)
        layout.addWidget(self._tool_table)

        # Installed System Images Section
        si_lbl = QLabel("Installed System Images:")
        si_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #9ca3af;")
        layout.addWidget(si_lbl)

        self._si_table = QTableWidget(0, 4)
        self._si_table.setHorizontalHeaderLabels(["Version", "API Level", "Edition / Tag", "ABI"])
        sihdr = self._si_table.horizontalHeader()
        sihdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        sihdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        sihdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        sihdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._si_table.verticalHeader().setVisible(False)
        self._si_table.setShowGrid(False)
        self._si_table.setFixedHeight(120)
        layout.addWidget(self._si_table)

        # Footer
        footer = QHBoxLayout()
        refresh_btn = QPushButton("Recheck Tools")
        refresh_btn.setIcon(get_icon("refresh-cw", size=12, color="#9ca3af"))
        refresh_btn.clicked.connect(self._refresh_diagnostics)
        footer.addWidget(refresh_btn)
        footer.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

        self._refresh_diagnostics()

    def _browse_sdk(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Android SDK Directory",
            self._path_input.text().strip() or str(Path.home()),
        )
        if folder:
            self._path_input.setText(folder)

    def _apply_sdk_path(self) -> None:
        raw = self._path_input.text().strip()
        if not raw:
            return
        p = Path(raw)
        if not p.is_dir():
            QMessageBox.warning(self, "Invalid Path", f"Directory does not exist:\n{raw}")
            return

        try:
            self._sdk_mgr.set_sdk_path(p)
            QMessageBox.information(
                self, "SDK Path Saved", "Android SDK location updated successfully."
            )
            self._refresh_diagnostics()
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Could not update SDK path: {exc}")

    def _refresh_diagnostics(self) -> None:
        status: AndroidEnvStatus = self._sdk_mgr.check_environment()
        if status.sdk_root:
            self._path_input.setText(str(status.sdk_root))

        # Overall Badge
        is_ready = status.is_ready
        badge_text = "READY" if is_ready else status.state.value.replace("_", " ")
        badge_bg = (
            "#064e3b" if is_ready else "#7f1d1d" if "MISSING" in status.state.value else "#78350f"
        )
        badge_fg = (
            "#34d399" if is_ready else "#f87171" if "MISSING" in status.state.value else "#fbbf24"
        )
        self._overall_badge.setText(badge_text)
        self._overall_badge.setStyleSheet(
            f"background-color: {badge_bg}; color: {badge_fg}; font-weight: 700; "
            "border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )

        # Populate Tools
        tools = [
            ("Android SDK", status.sdk_root is not None, str(status.sdk_root or "Not detected")),
            (
                "ADB (Platform-Tools)",
                status.adb_path is not None,
                status.adb_version or str(status.adb_path or "Missing"),
            ),
            (
                "Android Emulator",
                status.emulator_path is not None,
                status.emulator_version or str(status.emulator_path or "Missing"),
            ),
            (
                "AVD Manager",
                status.avdmanager_path is not None,
                str(status.avdmanager_path or "Missing"),
            ),
            (
                "SDK Manager",
                status.sdkmanager_path is not None,
                status.sdkmanager_version or str(status.sdkmanager_path or "Missing"),
            ),
            (
                "Java Runtime (JBR/JDK)",
                status.java_home is not None,
                str(status.java_home or "Missing (needed for AVD tools)"),
            ),
        ]

        self._tool_table.setRowCount(len(tools))
        for row, (name, available, info) in enumerate(tools):
            self._tool_table.setItem(row, 0, QTableWidgetItem(name))
            status_item = QTableWidgetItem("Ready" if available else "Missing")
            status_item.setIcon(
                get_icon(
                    "check-circle-2" if available else "x-circle",
                    size=13,
                    color="#10b981" if available else "#ef4444",
                )
            )
            status_item.setForeground(Qt.GlobalColor.green if available else Qt.GlobalColor.red)
            self._tool_table.setItem(row, 1, status_item)
            self._tool_table.setItem(row, 2, QTableWidgetItem(info))

        # Populate System Images
        images = self._sim_mgr.list_installed_images()
        self._si_table.setRowCount(len(images))
        for row, img in enumerate(images):
            self._si_table.setItem(row, 0, QTableWidgetItem(img.android_version))
            self._si_table.setItem(row, 1, QTableWidgetItem(f"API {img.api_level}"))
            self._si_table.setItem(row, 2, QTableWidgetItem(img.display_tag))
            self._si_table.setItem(row, 3, QTableWidgetItem(img.abi))
