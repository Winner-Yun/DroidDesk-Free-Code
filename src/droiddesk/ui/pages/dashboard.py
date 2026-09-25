"""Dashboard page. Aggregates project state, connected device status, active APK
details, and navigation shortcuts to inspection, testing, scanning, and release gate.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.core.models import Device
from droiddesk.ui.theme import TEXT, TEXT_MUTED, get_icon
from droiddesk.ui.widgets.card import Card, PageHeader, StatCard
from droiddesk.ui.widgets.device_bar import ApkInstallWorker
from droiddesk.ui.widgets.device_selector import DeviceSelector
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.status_pill import StatusPill


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


class DashboardPage(QWidget):
    upload_requested = Signal()
    navigate_requested = Signal(str)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._apk_path: Path | None = None
        self._installer_worker: ApkInstallWorker | None = None
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        header = PageHeader(
            "Home", "Current project state, and the last thing that happened in it."
        )
        outer.addWidget(header)

        # Empty state banner shown when no APK is selected
        self._empty_banner = EmptyStateWidget(
            title="No Active APK Selected",
            message=(
                "Upload or select an Android package (.apk / .aab) to populate "
                "live metrics, inspect manifests, and run automated tests."
            ),
            button_text="Upload APK",
            compact=True,
        )
        self._empty_banner.upload_requested.connect(self.upload_requested.emit)
        outer.addWidget(self._empty_banner)

        # Active APK card shown when an APK is selected
        self._apk_card = self._build_active_apk_card()
        outer.addWidget(self._apk_card)

        # Key metrics row (hidden / removed from layout per user request)
        self._stats_container = QWidget()
        stats_row = QHBoxLayout(self._stats_container)
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(14)

        self._stat_devices = StatCard("0", "Devices connected")
        self._stat_findings = StatCard("1", "Critical findings")
        self._stat_runs = StatCard("4", "Test runs today")

        stats_row.addWidget(self._stat_devices)
        stats_row.addWidget(self._stat_findings)
        stats_row.addWidget(self._stat_runs)
        self._stats_container.hide()

        # Bottom panels: APK Installer and Emulator History
        panels_row = QHBoxLayout()
        panels_row.setSpacing(14)
        panels_row.addWidget(self._build_apk_installer(), 1)
        panels_row.addWidget(self._build_emulator_history(), 1)
        outer.addLayout(panels_row, 1)

        # Wire live device updates
        self._ctx.device_service.devices_changed.connect(self._on_devices_changed)
        self._update_devices_stat()

        # Initial device history record and view population
        initial_devices: list[Device] = []
        if hasattr(self._ctx.device_service, "devices") and callable(
            self._ctx.device_service.devices
        ):
            initial_devices = self._ctx.device_service.devices()
        elif hasattr(self._ctx.device_service, "_devices"):
            initial_devices = getattr(self._ctx.device_service, "_devices", [])

        if hasattr(self._ctx.repository, "record_device"):
            for d in initial_devices:
                with contextlib.suppress(Exception):
                    self._ctx.repository.record_device(d)

        self._refresh_installer_apks()
        self._refresh_emulator_history()

        self.set_apk(None)

    def _build_active_apk_card(self) -> QWidget:
        card = Card("Active project")
        row = QHBoxLayout()
        row.setSpacing(16)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        self._apk_title_label = QLabel("No APK selected")
        self._apk_title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        info_col.addWidget(self._apk_title_label)

        self._apk_package_label = QLabel("com.example.app")
        self._apk_package_label.setProperty("role", "mono")
        info_col.addWidget(self._apk_package_label)

        tags_row = QHBoxLayout()
        tags_row.setSpacing(6)
        self._badge_version = QLabel("v1.0")
        self._badge_min = QLabel("min 24")
        self._badge_target = QLabel("target 34")
        self._badge_size = QLabel("-")

        for badge in (self._badge_version, self._badge_min, self._badge_target, self._badge_size):
            badge.setStyleSheet(
                "border: 1px solid #35373e; color: #8b8e94; border-radius: 3px; "
                "padding: 2px 8px; font-size: 11px;"
            )
            tags_row.addWidget(badge)
        tags_row.addStretch(1)
        info_col.addLayout(tags_row)
        row.addLayout(info_col, 1)

        # Quick action buttons to jump directly to other pages
        actions_col = QVBoxLayout()
        actions_col.setSpacing(6)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        btn_analyze = QPushButton("Inspect in analyzer")
        btn_analyze.clicked.connect(lambda: self.navigate_requested.emit("analyzer"))
        actions_row.addWidget(btn_analyze)

        btn_tests = QPushButton("Run tests")
        btn_tests.clicked.connect(self._on_run_tests_clicked)
        actions_row.addWidget(btn_tests)

        btn_security = QPushButton("Scan secrets")
        btn_security.clicked.connect(lambda: self.navigate_requested.emit("security"))
        actions_row.addWidget(btn_security)

        actions_col.addLayout(actions_row)
        row.addLayout(actions_col)

        card.body_layout().addLayout(row)
        return card

    def _build_apk_installer(self) -> QWidget:
        card = Card("APK Installer")
        subtitle = QLabel("Select an uploaded APK to install directly to a connected device.")
        subtitle.setProperty("role", "muted")
        card.body_layout().addWidget(subtitle)

        # APK selection row
        apk_label = QLabel("Select APK:")
        apk_label.setStyleSheet("font-weight: 600; font-size: 12px; margin-top: 4px;")
        card.body_layout().addWidget(apk_label)

        apk_select_row = QHBoxLayout()
        apk_select_row.setSpacing(8)

        self._installer_apk_combo = QComboBox()
        self._installer_apk_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        apk_select_row.addWidget(self._installer_apk_combo, 1)

        btn_upload = QPushButton("Upload APK")
        btn_upload.setIcon(get_icon("upload", size=14, color=TEXT))
        btn_upload.setIconSize(QSize(14, 14))
        btn_upload.clicked.connect(self.upload_requested.emit)
        apk_select_row.addWidget(btn_upload)

        btn_browse = QPushButton("Browse...")
        btn_browse.setIcon(get_icon("folder-open", size=14, color=TEXT_MUTED))
        btn_browse.setIconSize(QSize(14, 14))
        btn_browse.clicked.connect(self._on_installer_browse_clicked)
        apk_select_row.addWidget(btn_browse)

        card.body_layout().addLayout(apk_select_row)

        # Target device selection
        dev_label = QLabel("Target Device:")
        dev_label.setStyleSheet("font-weight: 600; font-size: 12px; margin-top: 4px;")
        card.body_layout().addWidget(dev_label)

        self._installer_dev_selector = DeviceSelector()
        devices: list[Device] = []
        if hasattr(self._ctx.device_service, "devices") and callable(
            self._ctx.device_service.devices
        ):
            devices = self._ctx.device_service.devices()
        elif hasattr(self._ctx.device_service, "_devices"):
            devices = getattr(self._ctx.device_service, "_devices", [])
        self._installer_dev_selector.set_devices(devices)
        card.body_layout().addWidget(self._installer_dev_selector)

        # Action button and progress
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self._installer_run_btn = QPushButton("Install to device")
        self._installer_run_btn.setProperty("role", "primary")
        self._installer_run_btn.setIcon(get_icon("smartphone", size=14, color="#ffffff"))
        self._installer_run_btn.setIconSize(QSize(14, 14))
        self._installer_run_btn.clicked.connect(self._on_installer_run_clicked)
        action_row.addWidget(self._installer_run_btn)
        action_row.addStretch(1)

        card.body_layout().addLayout(action_row)

        # Progress bar
        self._installer_progress = QProgressBar()
        self._installer_progress.setFixedHeight(6)
        self._installer_progress.setTextVisible(False)
        self._installer_progress.hide()
        card.body_layout().addWidget(self._installer_progress)

        # Status feedback label
        self._installer_status_label = QLabel("")
        self._installer_status_label.setProperty("role", "muted")
        card.body_layout().addWidget(self._installer_status_label)

        card.body_layout().addStretch(1)
        return card

    def _build_emulator_history(self) -> QWidget:
        card = Card("Emulator History")

        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)
        subtitle = QLabel("Saved connection history for all emulators and devices.")
        subtitle.setProperty("role", "muted")
        sub_row.addWidget(subtitle, 1)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("role", "secondary")
        btn_refresh.setIcon(get_icon("rotate-cw", size=13, color=TEXT_MUTED))
        btn_refresh.setIconSize(QSize(13, 13))
        btn_refresh.clicked.connect(self._refresh_emulator_history)
        sub_row.addWidget(btn_refresh)

        card.body_layout().addLayout(sub_row)

        # History table
        self._history_table = QTableWidget(0, 4)
        self._history_table.setHorizontalHeaderLabels(
            ["Status", "Device / Model", "Platform", "Last Connected"]
        )
        header = self._history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        card.body_layout().addWidget(self._history_table, 1)

        self._history_empty_label = QLabel(
            "No emulator history recorded yet.\nConnect an emulator or device to track history."
        )
        self._history_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._history_empty_label.setProperty("role", "muted")
        self._history_empty_label.hide()
        card.body_layout().addWidget(self._history_empty_label)

        return card

    def _refresh_installer_apks(self) -> None:
        current_selection = self._installer_apk_combo.currentData()
        self._installer_apk_combo.clear()

        paths: list[Path] = []
        labels: list[str] = []

        if self._apk_path and self._apk_path.is_file():
            paths.append(self._apk_path)
            labels.append(f"{self._apk_path.name} (Active)")

        if hasattr(self._ctx.repository, "list_apks") and callable(self._ctx.repository.list_apks):
            try:
                stored = self._ctx.repository.list_apks()
                for info in stored:
                    if info.file_path and info.file_path not in paths and info.file_path.is_file():
                        paths.append(info.file_path)
                        pkg = info.package_name or "APK"
                        labels.append(f"{info.file_path.name} ({pkg})")
            except Exception:
                pass

        if not paths:
            self._installer_apk_combo.addItem("No APK uploaded", None)
            self._installer_apk_combo.setEnabled(False)
        else:
            self._installer_apk_combo.setEnabled(True)
            for path, label in zip(paths, labels, strict=False):
                self._installer_apk_combo.addItem(label, path)

            if current_selection in paths:
                idx = paths.index(current_selection)
                self._installer_apk_combo.setCurrentIndex(idx)

    def _on_installer_browse_clicked(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select APK File",
            "",
            "Android Packages (*.apk *.aab);;All Files (*)",
        )
        if chosen:
            chosen_path = Path(chosen)
            all_paths = [
                self._installer_apk_combo.itemData(i)
                for i in range(self._installer_apk_combo.count())
            ]
            if chosen_path not in all_paths:
                if (
                    self._installer_apk_combo.count() == 1
                    and self._installer_apk_combo.itemData(0) is None
                ):
                    self._installer_apk_combo.clear()
                    self._installer_apk_combo.setEnabled(True)
                self._installer_apk_combo.addItem(f"{chosen_path.name} (Custom)", chosen_path)

            for i in range(self._installer_apk_combo.count()):
                if self._installer_apk_combo.itemData(i) == chosen_path:
                    self._installer_apk_combo.setCurrentIndex(i)
                    break

    def _on_installer_run_clicked(self) -> None:
        if self._installer_worker and self._installer_worker.isRunning():
            self._installer_worker.cancel()
            self._installer_run_btn.setText("Install to device")
            self._installer_run_btn.setIcon(get_icon("smartphone", size=14, color="#ffffff"))
            self._installer_status_label.setText("Installation cancelled.")
            return

        apk_path = self._installer_apk_combo.currentData()
        if not isinstance(apk_path, Path) or not apk_path.is_file():
            QMessageBox.warning(
                self,
                "No APK Selected",
                "No uploaded APK file selected.\n\n"
                "Please select or upload an APK file before installing.",
            )
            return

        device = self._installer_dev_selector.selected_device()
        if not device or device.state != "device":
            QMessageBox.warning(
                self,
                "No Emulator Connected",
                "No Android device or emulator is currently connected.\n\n"
                "Please connect an Android device or start an emulator to install the APK.",
            )
            return

        self._installer_run_btn.setText("Cancel")
        self._installer_run_btn.setIcon(get_icon("square", size=14, color="#ffffff"))
        self._installer_progress.setRange(0, 1)
        self._installer_progress.setValue(0)
        self._installer_progress.show()
        self._installer_status_label.setText(
            f"Installing {apk_path.name} to {device.model or device.serial}..."
        )
        self._installer_status_label.setStyleSheet("")

        self._installer_worker = ApkInstallWorker(
            device_service=self._ctx.device_service,
            serial=device.serial,
            apk_paths=[apk_path],
        )
        self._installer_worker.apk_finished.connect(self._on_installer_apk_finished)
        self._installer_worker.all_finished.connect(self._on_installer_all_finished)
        self._installer_worker.start()

    def _on_installer_apk_finished(self, path: Path, ok: bool, message: str) -> None:
        if ok:
            self._installer_status_label.setText(f"Successfully installed {path.name}!")
            self._installer_status_label.setStyleSheet("color: #27ae60; font-weight: 600;")
        else:
            self._installer_status_label.setText(f"Installation failed: {message}")
            self._installer_status_label.setStyleSheet("color: #e0574a; font-weight: 600;")

    def _on_installer_all_finished(self, successes: int, total: int) -> None:
        self._installer_run_btn.setText("Install to device")
        self._installer_run_btn.setIcon(get_icon("smartphone", size=14, color="#ffffff"))
        self._installer_progress.setValue(1)
        self._installer_progress.hide()

    def _refresh_emulator_history(self) -> None:
        if not hasattr(self._ctx.repository, "list_device_history") or not callable(
            self._ctx.repository.list_device_history
        ):
            return

        try:
            history = self._ctx.repository.list_device_history()
        except Exception:
            history = []

        if not history:
            self._history_table.setRowCount(0)
            self._history_table.hide()
            self._history_empty_label.show()
            return

        self._history_empty_label.hide()
        self._history_table.show()

        active_serials: set[str] = set()
        if hasattr(self._ctx.device_service, "devices") and callable(
            self._ctx.device_service.devices
        ):
            active_serials = {d.serial for d in self._ctx.device_service.devices()}
        elif hasattr(self._ctx.device_service, "_devices"):
            active_serials = {d.serial for d in getattr(self._ctx.device_service, "_devices", [])}

        self._history_table.setRowCount(len(history))
        for row_idx, item in enumerate(history):
            serial = str(item.get("serial", ""))
            model = str(item.get("model", "") or serial)
            state = str(item.get("state", "device"))
            version = str(item.get("android_version", "-"))
            api = item.get("api_level", 0)
            abi = str(item.get("abi", "-"))
            last_conn = str(item.get("last_connected", "-"))

            is_online = serial in active_serials

            status_text = "Online" if is_online else "Offline"
            status_type = "pass" if is_online else "info"
            pill_widget = QWidget()
            pill_layout = QHBoxLayout(pill_widget)
            pill_layout.setContentsMargins(4, 2, 4, 2)
            pill_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill_layout.addWidget(StatusPill(status_text, status_type))
            self._history_table.setCellWidget(row_idx, 0, pill_widget)

            dev_item = QTableWidgetItem(f"{model} ({serial})")
            dev_item.setToolTip(f"Serial: {serial}\nState: {state}\nABI: {abi}")
            self._history_table.setItem(row_idx, 1, dev_item)

            if version and version != "-" and api:
                platform_str = f"Android {version} (API {api})"
            elif api:
                platform_str = f"API {api}"
            elif version and version != "-":
                platform_str = f"Android {version}"
            else:
                platform_str = "-"
            plat_item = QTableWidgetItem(platform_str)
            plat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._history_table.setItem(row_idx, 2, plat_item)

            conn_item = QTableWidgetItem(last_conn)
            conn_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            conn_item.setForeground(Qt.GlobalColor.gray)
            self._history_table.setItem(row_idx, 3, conn_item)

    def _update_devices_stat(self, devices: list[Device] | None = None) -> None:
        if devices is None:
            if hasattr(self._ctx.device_service, "devices") and callable(
                self._ctx.device_service.devices
            ):
                devices = self._ctx.device_service.devices()
            else:
                devices = getattr(self._ctx.device_service, "_devices", [])

        count = len(devices)
        self._stat_devices.set_value(str(count))
        if count == 0:
            self._stat_devices.set_caption("No emulator connected")
        else:
            plural = "devices" if count != 1 else "device"
            self._stat_devices.set_caption(f"Connected {plural}")

    def _on_devices_changed(self, devices: list[Device]) -> None:
        if hasattr(self._ctx.repository, "record_device"):
            for d in devices:
                with contextlib.suppress(Exception):
                    self._ctx.repository.record_device(d)
        if hasattr(self, "_installer_dev_selector"):
            self._installer_dev_selector.set_devices(devices)
        self._update_devices_stat(devices)
        if hasattr(self, "_history_table"):
            self._refresh_emulator_history()

    def set_apk(self, path: Path | None) -> None:
        self._apk_path = path
        if hasattr(self, "_installer_apk_combo"):
            self._refresh_installer_apks()
        if path is None:
            self._empty_banner.show()
            self._apk_card.hide()
        else:
            self._empty_banner.hide()
            self._apk_title_label.setText(path.name)
            try:
                info = self._ctx.apk_service.inspect(path)
                self._apk_package_label.setText(info.package_name)
                v_name = info.version_name or str(info.version_code or "1.0")
                self._badge_version.setText(f"v{v_name}")
                self._badge_min.setText(f"min {info.min_sdk or '?'}")
                self._badge_target.setText(f"target {info.target_sdk or '?'}")
            except Exception:
                self._apk_package_label.setText("Active package")
                self._badge_version.setText("v1.0")
                self._badge_min.setText("min 21")
                self._badge_target.setText("target 34")

            try:
                if path.is_file():
                    self._badge_size.setText(_format_size(path.stat().st_size))
                else:
                    self._badge_size.setText("-")
            except OSError:
                self._badge_size.setText("-")

            self._apk_card.show()


    def _on_run_tests_clicked(self) -> None:
        if hasattr(self._ctx.device_service, "devices") and callable(
            self._ctx.device_service.devices
        ):
            devices = self._ctx.device_service.devices()
        else:
            devices = getattr(self._ctx.device_service, "_devices", [])

        if not devices:
            QMessageBox.warning(
                self,
                "No Emulator Connected",
                "No Android device or emulator is currently connected.\n\n"
                "Please connect an Android device via USB/Wi-Fi or start an emulator "
                "to run tests.",
            )
            return
        self.navigate_requested.emit("tester")
