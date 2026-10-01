"""APK Action Dialog: inspect, install, launch, and manage applications on selected devices."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.application.apk_manager import ApkManager
from droiddesk.core.models import ApkInfo
from droiddesk.device.models import ManagedDevice
from droiddesk.ui.theme import get_icon


class _InstallWorker(QThread):
    finished_result = Signal(bool, str)

    def __init__(
        self,
        apk_manager: ApkManager,
        serial: str,
        apk_path: Path,
        launch_after: bool,
        launchable_activity: str | None,
        package_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._mgr = apk_manager
        self._serial = serial
        self._apk_path = apk_path
        self._launch_after = launch_after
        self._activity = launchable_activity
        self._pkg = package_name

    def run(self) -> None:
        ok, msg = self._mgr.install_apk(self._serial, self._apk_path)
        if not ok:
            self.finished_result.emit(False, msg)
            return

        if self._launch_after:
            launch_ok, launch_msg = self._mgr.launch_app(self._serial, self._pkg, self._activity)
            if launch_ok:
                self.finished_result.emit(True, f"APK installed and launched: {self._pkg}")
            else:
                self.finished_result.emit(True, f"APK installed, but launch failed: {launch_msg}")
        else:
            self.finished_result.emit(True, "APK installed successfully.")


class ApkActionDialog(QDialog):
    """Dialog for inspecting an APK and installing/launching on an Android device."""

    def __init__(
        self,
        apk_manager: ApkManager,
        devices: list[ManagedDevice],
        initial_device: ManagedDevice | None = None,
        initial_apk_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._apk_manager = apk_manager
        self._devices = [d for d in devices if d.is_online]
        self._selected_apk_info: ApkInfo | None = None
        self._launchable_activity: str | None = None
        self._worker: _InstallWorker | None = None

        self.setWindowTitle("APK Operations - Install & Launch")
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
            QLineEdit, QComboBox {
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
        icon_lbl.setPixmap(get_icon("box", size=22, color="#3b82f6").pixmap(22, 22))
        h_row.addWidget(icon_lbl)
        title = QLabel("Install & Launch APK")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        h_row.addWidget(title)
        h_row.addStretch(1)
        layout.addLayout(h_row)

        # 1. Device Selection
        dev_label = QLabel("Target Device:")
        dev_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #9ca3af;")
        layout.addWidget(dev_label)

        self._dev_combo = QComboBox()
        for dev in self._devices:
            dev_type = "Physical" if dev.is_physical else "Emulator"
            self._dev_combo.addItem(f"{dev.name} ({dev.serial}) [{dev_type}]", dev)

        # Select initial device if provided
        if initial_device:
            for idx in range(self._dev_combo.count()):
                d = self._dev_combo.itemData(idx)
                if d.id == initial_device.id:
                    self._dev_combo.setCurrentIndex(idx)
                    break

        layout.addWidget(self._dev_combo)

        # 2. APK Selection
        apk_label = QLabel("APK Package File:")
        apk_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #9ca3af;")
        layout.addWidget(apk_label)

        apk_row = QHBoxLayout()
        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText("Select an Android .apk package file...")
        self._path_input.textChanged.connect(self._inspect_selected_apk)
        apk_row.addWidget(self._path_input, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_apk)
        apk_row.addWidget(browse_btn)
        layout.addLayout(apk_row)

        # 3. APK Metadata Summary Card
        self._meta_card = QFrame()
        self._meta_card.setStyleSheet(
            "background-color: #212226; border: 1px solid #2c2d33; border-radius: 6px; padding: 10px;"
        )
        meta_layout = QVBoxLayout(self._meta_card)
        meta_layout.setContentsMargins(10, 8, 10, 8)
        meta_layout.setSpacing(6)

        self._pkg_lbl = QLabel("Package: -")
        self._pkg_lbl.setStyleSheet("font-weight: 600; font-size: 12px; color: #3b82f6;")
        meta_layout.addWidget(self._pkg_lbl)

        self._ver_lbl = QLabel("Version: -")
        self._ver_lbl.setStyleSheet("font-size: 11px; color: #9ca3af;")
        meta_layout.addWidget(self._ver_lbl)

        self._act_lbl = QLabel("Launchable Activity: -")
        self._act_lbl.setStyleSheet("font-size: 11px; color: #9ca3af;")
        meta_layout.addWidget(self._act_lbl)

        layout.addWidget(self._meta_card)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size: 11px; color: #8b8e94;")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        btn_row.addStretch(1)

        self._launch_btn = QPushButton("Launch Only")
        self._launch_btn.clicked.connect(self._on_launch_clicked)
        btn_row.addWidget(self._launch_btn)

        self._install_btn = QPushButton("Install")
        self._install_btn.clicked.connect(lambda: self._on_install_clicked(launch=False))
        btn_row.addWidget(self._install_btn)

        self._install_launch_btn = QPushButton("Install & Launch")
        self._install_launch_btn.setStyleSheet(
            "QPushButton { background: #2563eb; border: 1px solid #3b82f6; color: #ffffff; "
            "border-radius: 4px; padding: 7px 18px; font-weight: 600; }"
            "QPushButton:hover { background: #1d4ed8; }"
        )
        self._install_launch_btn.clicked.connect(lambda: self._on_install_clicked(launch=True))
        btn_row.addWidget(self._install_launch_btn)

        layout.addLayout(btn_row)

        if initial_apk_path and initial_apk_path.is_file():
            self._path_input.setText(str(initial_apk_path))

    def _browse_apk(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select APK File", "", "Android Packages (*.apk)"
        )
        if file_path:
            self._path_input.setText(file_path)

    def _inspect_selected_apk(self, path_str: str) -> None:
        p = Path(path_str.strip())
        if not p.is_file():
            self._pkg_lbl.setText("Package: -")
            self._ver_lbl.setText("Version: -")
            self._act_lbl.setText("Launchable Activity: -")
            self._selected_apk_info = None
            self._launchable_activity = None
            return

        try:
            info = self._apk_manager.inspect_apk(p)
            self._selected_apk_info = info
            self._launchable_activity = self._apk_manager.find_launchable_activity(p)

            self._pkg_lbl.setText(f"Package: {info.package_name}")
            v_name = info.version_name or "-"
            v_code = info.version_code or "-"
            min_s = info.min_sdk or "-"
            tgt_s = info.target_sdk or "-"
            self._ver_lbl.setText(
                f"Version: {v_name} ({v_code}) | Min: {min_s} | Target: {tgt_s}"
            )
            self._act_lbl.setText(
                f"Launchable Activity: {self._launchable_activity or 'Default Monkey'}"
            )
        except Exception as exc:
            self._pkg_lbl.setText(f"Error parsing APK: {exc}")

    def _get_target_serial(self) -> str | None:
        dev: ManagedDevice | None = self._dev_combo.currentData()
        if dev and dev.serial:
            return dev.serial
        return None

    def _on_install_clicked(self, launch: bool) -> None:
        serial = self._get_target_serial()
        if not serial:
            QMessageBox.warning(self, "No Device", "Please select a connected and online device.")
            return

        p = Path(self._path_input.text().strip())
        if not p.is_file():
            QMessageBox.warning(self, "Missing APK", "Please select a valid .apk file.")
            return

        if not self._selected_apk_info:
            QMessageBox.warning(
                self, "Inspection Failed", "Could not inspect APK package information."
            )
            return

        self._set_busy(True, "Installing APK onto device...")
        self._worker = _InstallWorker(
            apk_manager=self._apk_manager,
            serial=serial,
            apk_path=p,
            launch_after=launch,
            launchable_activity=self._launchable_activity,
            package_name=self._selected_apk_info.package_name,
            parent=self,
        )
        self._worker.finished_result.connect(self._on_install_finished)
        self._worker.start()

    def _on_launch_clicked(self) -> None:
        serial = self._get_target_serial()
        if not serial:
            QMessageBox.warning(self, "No Device", "Please select a connected and online device.")
            return

        if not self._selected_apk_info:
            QMessageBox.warning(
                self, "No Package", "Please select an APK to determine package name."
            )
            return

        self._set_busy(True, "Launching application...")
        ok, msg = self._apk_manager.launch_app(
            serial=serial,
            package_name=self._selected_apk_info.package_name,
            activity_name=self._launchable_activity,
        )
        self._set_busy(False)
        if ok:
            QMessageBox.information(self, "App Launched", msg)
        else:
            QMessageBox.warning(self, "Launch Failed", msg)

    def _on_install_finished(self, success: bool, message: str) -> None:
        self._set_busy(False)
        self._status_lbl.setText(message)
        if success:
            QMessageBox.information(self, "Installation Succeeded", message)
        else:
            QMessageBox.warning(self, "Installation Failed", message)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._progress.setVisible(busy)
        self._install_btn.setEnabled(not busy)
        self._install_launch_btn.setEnabled(not busy)
        self._launch_btn.setEnabled(not busy)
        self._status_lbl.setText(message)
