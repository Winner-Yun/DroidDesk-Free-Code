from __future__ import annotations

from pathlib import Path
from typing import override

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QDialog,
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

from droiddesk.core.models import Device
from droiddesk.services.device_service import DeviceService
from droiddesk.ui.widgets.device_selector import DeviceSelector


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


class ApkInstallWorker(QThread):
    progress = Signal(int, int)  # current, total
    apk_started = Signal(object)  # Path
    apk_finished = Signal(object, bool, str)  # Path, success, error_message
    all_finished = Signal(int, int)  # successes, total

    def __init__(
        self,
        device_service: DeviceService,
        serial: str,
        apk_paths: list[Path],
    ) -> None:
        super().__init__()
        self._service = device_service
        self._serial = serial
        self._paths = list(apk_paths)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @override
    def run(self) -> None:
        total = len(self._paths)
        successes = 0

        for i, path in enumerate(self._paths):
            if self._cancelled:
                break
            self.apk_started.emit(path)

            if path.suffix.lower() == ".aab":
                self.apk_finished.emit(path, False, "AAB requires bundletool build")
                self.progress.emit(i + 1, total)
                continue

            try:
                ok = self._service.install_apk(self._serial, path)
                msg = "Installed successfully" if ok else "ADB installation failed"
            except Exception as exc:
                ok = False
                msg = str(exc)

            if ok:
                successes += 1
            self.apk_finished.emit(path, ok, msg)
            self.progress.emit(i + 1, total)

        self.all_finished.emit(successes, total)


class ApkUploadDialog(QDialog):
    """Dialog displaying uploaded APKs with target device confirmation and progress."""

    def __init__(
        self,
        device_service: DeviceService,
        initial_device: Device | None = None,
        apk_paths: list[Path] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = device_service
        self._apk_paths: list[Path] = []
        self._worker: ApkInstallWorker | None = None

        self.setWindowTitle("Upload & Install APKs")
        self.resize(620, 440)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Title & instruction
        title_label = QLabel("Upload & Install APKs")
        title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title_label)

        sub_label = QLabel(
            "Batch install APK files to the selected Android device. "
            "You can drag and drop additional files here."
        )
        sub_label.setProperty("role", "muted")
        sub_label.setWordWrap(True)
        layout.addWidget(sub_label)

        # Target device selection
        dev_row = QHBoxLayout()
        dev_row.setSpacing(10)
        dev_label = QLabel("Target Device:")
        dev_label.setStyleSheet("font-weight: 600;")
        self._dev_selector = DeviceSelector()
        self._dev_selector.set_devices(device_service.devices())
        if initial_device:
            devices = device_service.devices()
            for idx, d in enumerate(devices):
                if d.serial == initial_device.serial:
                    self._dev_selector.setCurrentIndex(idx)
                    break
        dev_row.addWidget(dev_label)
        dev_row.addWidget(self._dev_selector, 1)
        layout.addLayout(dev_row)

        # Files table
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["File Name", "Size", "Status"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)

        # Progress bar & message
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setProperty("role", "muted")
        layout.addWidget(self._status_label)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._add_btn = QPushButton("＋  Add Files...")
        self._add_btn.clicked.connect(self._on_add_files_clicked)
        btn_row.addWidget(self._add_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._on_clear_clicked)
        btn_row.addWidget(self._clear_btn)

        btn_row.addStretch(1)

        self._install_btn = QPushButton("▶  Install to Device")
        self._install_btn.setProperty("role", "primary")
        self._install_btn.clicked.connect(self._on_install_clicked)
        btn_row.addWidget(self._install_btn)

        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self._on_close_clicked)
        btn_row.addWidget(self._close_btn)

        layout.addLayout(btn_row)

        if apk_paths:
            self.add_apk_paths(apk_paths)

    def add_apk_paths(self, paths: list[Path]) -> None:
        for p in paths:
            if p not in self._apk_paths and p.is_file():
                self._apk_paths.append(p)
                row = self._table.rowCount()
                self._table.insertRow(row)

                # Name
                name_item = QTableWidgetItem(f"⛁  {p.name}")
                name_item.setToolTip(str(p))
                self._table.setItem(row, 0, name_item)

                # Size
                try:
                    size_str = _format_size(p.stat().st_size)
                except OSError:
                    size_str = "—"
                size_item = QTableWidgetItem(size_str)
                size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 1, size_item)

                # Status
                status_item = QTableWidgetItem("Ready")
                status_item.setForeground(Qt.GlobalColor.gray)
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 2, status_item)

        self._status_label.setText(f"{len(self._apk_paths)} APK file(s) loaded.")
        self._install_btn.setEnabled(len(self._apk_paths) > 0)

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
            self.add_apk_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _on_add_files_clicked(self) -> None:
        chosen, _ = QFileDialog.getOpenFileNames(
            self,
            "Select APK Files to Upload",
            "",
            "Android Packages (*.apk *.aab);;All Files (*)",
        )
        if chosen:
            self.add_apk_paths([Path(p) for p in chosen])

    def _on_clear_clicked(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._apk_paths.clear()
        self._table.setRowCount(0)
        self._status_label.setText("No files loaded.")
        self._install_btn.setEnabled(False)

    def _on_install_clicked(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._install_btn.setText("▶  Install to Device")
            self._status_label.setText("Installation cancelled.")
            return

        device = self._dev_selector.selected_device()
        if not device or device.state != "device":
            msg = (
                "No Android device is currently connected or authorized.\n\n"
                "Please connect an Android device via USB or Wi-Fi with USB debugging enabled."
            )
            QMessageBox.warning(self, "No Device Connected", msg)
            self._status_label.setText("Error: No device connected or authorized.")
            self._status_label.setStyleSheet("color: #e0574a;")
            return

        if not self._apk_paths:
            QMessageBox.warning(
                self,
                "No APK Files",
                "No APK files are available to install. Please add APK files first.",
            )
            self._status_label.setText("Error: No APK files to install.")
            self._status_label.setStyleSheet("color: #e0574a;")
            return

        # Prepare UI for installation
        self._install_btn.setText("■  Cancel")
        self._add_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)
        self._dev_selector.setEnabled(False)
        self._progress_bar.setRange(0, len(self._apk_paths))
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._status_label.setStyleSheet("")
        self._status_label.setText(f"Starting installation to {device.model or device.serial}...")

        # Reset statuses
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 2)
            if item:
                item.setText("Pending")
                item.setForeground(Qt.GlobalColor.gray)

        # Launch worker
        self._worker = ApkInstallWorker(
            device_service=self._service,
            serial=device.serial,
            apk_paths=self._apk_paths,
        )
        self._worker.apk_started.connect(self._on_apk_started)
        self._worker.apk_finished.connect(self._on_apk_finished)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.all_finished.connect(self._on_all_finished)
        self._worker.start()

    def _find_row_for_path(self, path: Path) -> int:
        for idx, p in enumerate(self._apk_paths):
            if p == path:
                return idx
        return -1

    def _on_apk_started(self, path: Path) -> None:
        row = self._find_row_for_path(path)
        if row >= 0:
            item = self._table.item(row, 2)
            if item:
                item.setText("Installing...")
                item.setForeground(Qt.GlobalColor.cyan)
        self._status_label.setText(f"Installing {path.name}...")

    def _on_apk_finished(self, path: Path, ok: bool, message: str) -> None:
        row = self._find_row_for_path(path)
        if row >= 0:
            item = self._table.item(row, 2)
            if item:
                item.setText("✓ Installed" if ok else "✗ Failed")
                item.setToolTip(message)
                item.setForeground(
                    Qt.GlobalColor.green if ok else Qt.GlobalColor.red
                )

    def _on_worker_progress(self, current: int, total: int) -> None:
        self._progress_bar.setValue(current)

    def _on_all_finished(self, successes: int, total: int) -> None:
        self._install_btn.setText("▶  Install to Device")
        self._add_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        self._dev_selector.setEnabled(True)

        if successes == total:
            self._status_label.setText(f"Done: All {total} APK(s) installed successfully!")
            self._status_label.setStyleSheet("color: #27ae60; font-weight: 600;")
        else:
            failed = total - successes
            self._status_label.setText(f"Done: {successes} succeeded, {failed} failed.")
            self._status_label.setStyleSheet("color: #e0574a; font-weight: 600;")

    def _on_close_clicked(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1000)
        self.accept()


class DeviceBar(QWidget):
    """Appbar device controls: target device selector."""

    def __init__(self, device_service: DeviceService) -> None:
        super().__init__()
        self.setObjectName("deviceBar")
        self._device_service = device_service

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._device_label = QLabel("TARGET DEVICE:")
        self._device_selector = DeviceSelector()

        layout.addWidget(self._device_label)
        layout.addWidget(self._device_selector)

        device_service.devices_changed.connect(self._device_selector.set_devices)
        self._device_selector.set_devices(device_service.devices())

    def selected_device(self) -> Device | None:
        return self._device_selector.selected_device()

    def device_selector(self) -> DeviceSelector:
        return self._device_selector