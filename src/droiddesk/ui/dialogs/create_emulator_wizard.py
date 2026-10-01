"""Multi-step Create Emulator Wizard dialog."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from droiddesk.android.avd_manager import AvdManager
from droiddesk.android.models import DeviceProfile, SystemImage
from droiddesk.android.system_image_manager import ImageDownloadThread, SystemImageManager
from droiddesk.infra.tools import ToolLocator
from droiddesk.ui.theme import get_icon


class CreateEmulatorWizard(QDialog):
    """Multi-step wizard for configuring and creating an Android Virtual Device."""

    emulator_created = Signal(str)  # avd_name

    def __init__(
        self,
        avd_manager: AvdManager,
        system_image_manager: SystemImageManager,
        tool_locator: ToolLocator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._avd_mgr = avd_manager
        self._sim_mgr = system_image_manager
        self._tool_locator = tool_locator
        self._current_step = 0
        self._download_worker: ImageDownloadThread | None = None

        self._selected_profile: DeviceProfile | None = None
        self._selected_image: SystemImage | None = None

        self.setWindowTitle("Create Android Virtual Device")
        self.setMinimumSize(700, 520)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1a1b1e;
                color: #e5e7eb;
            }
            QLabel {
                color: #e5e7eb;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #212226;
                color: #ffffff;
                border: 1px solid #35373e;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border-color: #3b82f6;
            }
            """
        )

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(24, 20, 24, 20)
        outer_layout.setSpacing(16)

        # Step Indicator Header
        self._step_header = self._build_step_header()
        outer_layout.addWidget(self._step_header)

        # Stacked Pages
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step1_device())
        self._stack.addWidget(self._build_step2_version())
        self._stack.addWidget(self._build_step3_config())
        self._stack.addWidget(self._build_step4_progress())
        outer_layout.addWidget(self._stack, 1)

        # Navigation Buttons Footer
        self._footer = self._build_footer()
        outer_layout.addWidget(self._footer)

        self._update_step_view()

    # -------------------------------------------------------------------------
    # Step Indicator Header
    # -------------------------------------------------------------------------
    def _build_step_header(self) -> QWidget:
        header = QFrame()
        header.setStyleSheet("background-color: #212226; border-radius: 6px; padding: 6px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 6, 12, 6)

        self._step_labels: list[QLabel] = []
        steps = ["1. Device Profile", "2. Android Version", "3. Configuration", "4. Create"]

        for i, title in enumerate(steps):
            lbl = QLabel(title)
            lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #8b8e94;")
            h_layout.addWidget(lbl)
            self._step_labels.append(lbl)
            if i < len(steps) - 1:
                sep = QLabel("→")
                sep.setStyleSheet("color: #4b5563; font-weight: 700;")
                h_layout.addWidget(sep)

        return header

    # -------------------------------------------------------------------------
    # Step 1: Device Profile Selection
    # -------------------------------------------------------------------------
    def _build_step1_device(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Step 1: Choose Device Profile")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        layout.addWidget(title)

        desc = QLabel("Select an Android hardware device definition for your virtual device.")
        desc.setStyleSheet("font-size: 12px; color: #8b8e94;")
        layout.addWidget(desc)

        # Search Bar
        search_box = QHBoxLayout()
        self._dev_search = QLineEdit()
        self._dev_search.setPlaceholderText("Search device profiles (e.g. Pixel, Tablet, Phone)...")
        self._dev_search.textChanged.connect(self._filter_device_profiles)
        search_box.addWidget(self._dev_search)
        layout.addLayout(search_box)

        # Device Profiles Table
        self._dev_table = QTableWidget(0, 4)
        self._dev_table.setHorizontalHeaderLabels(["Name", "OEM", "Screen Size", "Resolution"])
        hdr = self._dev_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._dev_table.verticalHeader().setVisible(False)
        self._dev_table.setShowGrid(False)
        self._dev_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._dev_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._dev_table.itemSelectionChanged.connect(self._on_profile_selected)
        layout.addWidget(self._dev_table, 1)

        self._populate_device_profiles()
        return page

    def _populate_device_profiles(self) -> None:
        self._all_profiles = self._avd_mgr.list_device_profiles()
        self._filter_device_profiles("")

    def _filter_device_profiles(self, query: str) -> None:
        q = query.strip().lower()
        filtered = [
            p
            for p in self._all_profiles
            if not q or q in p.name.lower() or q in p.oem.lower() or q in p.id.lower()
        ]
        self._dev_table.setRowCount(len(filtered))

        for row, prof in enumerate(filtered):
            name_item = QTableWidgetItem(prof.name)
            name_item.setData(Qt.ItemDataRole.UserRole, prof)
            self._dev_table.setItem(row, 0, name_item)
            self._dev_table.setItem(row, 1, QTableWidgetItem(prof.oem))
            self._dev_table.setItem(row, 2, QTableWidgetItem(prof.screen_size or "-"))
            self._dev_table.setItem(row, 3, QTableWidgetItem(prof.resolution or "-"))

        if filtered:
            self._dev_table.selectRow(0)

    def _on_profile_selected(self) -> None:
        rows = self._dev_table.selectionModel().selectedRows()
        if rows:
            item = self._dev_table.item(rows[0].row(), 0)
            if item:
                self._selected_profile = item.data(Qt.ItemDataRole.UserRole)
                self._update_next_button_state()

    # -------------------------------------------------------------------------
    # Step 2: System Image & Android Version Selection
    # -------------------------------------------------------------------------
    def _build_step2_version(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Step 2: Choose Android Version & System Image")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        layout.addWidget(title)

        desc = QLabel(
            "Installed images can be used immediately. "
            "Missing images can be downloaded via SDK Manager."
        )
        desc.setStyleSheet("font-size: 12px; color: #8b8e94;")
        layout.addWidget(desc)

        # Image Table
        self._img_table = QTableWidget(0, 5)
        self._img_table.setHorizontalHeaderLabels(
            ["Android Version", "API Level", "Edition / Tag", "ABI", "Status"]
        )
        hdr = self._img_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._img_table.verticalHeader().setVisible(False)
        self._img_table.setShowGrid(False)
        self._img_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._img_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._img_table.itemSelectionChanged.connect(self._on_image_selected)
        layout.addWidget(self._img_table, 1)

        self._populate_system_images()
        return page

    def _populate_system_images(self) -> None:
        images = self._sim_mgr.list_all_available_images()
        self._img_table.setRowCount(len(images))

        for row, img in enumerate(images):
            ver_item = QTableWidgetItem(img.android_version)
            ver_item.setData(Qt.ItemDataRole.UserRole, img)
            self._img_table.setItem(row, 0, ver_item)
            self._img_table.setItem(row, 1, QTableWidgetItem(f"API {img.api_level}"))
            self._img_table.setItem(row, 2, QTableWidgetItem(img.display_tag))
            self._img_table.setItem(row, 3, QTableWidgetItem(img.abi))

            status_str = "Installed" if img.is_installed else "Download Required"
            status_item = QTableWidgetItem(status_str)
            status_item.setIcon(
                get_icon(
                    "check-circle-2" if img.is_installed else "arrow-down-circle",
                    size=13,
                    color="#10b981" if img.is_installed else "#f59e0b",
                )
            )
            if img.is_installed:
                status_item.setForeground(Qt.GlobalColor.green)
            else:
                status_item.setForeground(Qt.GlobalColor.yellow)
            self._img_table.setItem(row, 4, status_item)

        if images:
            self._img_table.selectRow(0)

    def _on_image_selected(self) -> None:
        rows = self._img_table.selectionModel().selectedRows()
        if rows:
            item = self._img_table.item(rows[0].row(), 0)
            if item:
                self._selected_image = item.data(Qt.ItemDataRole.UserRole)
                self._update_next_button_state()

    # -------------------------------------------------------------------------
    # Step 3: Emulator Configuration
    # -------------------------------------------------------------------------
    def _build_step3_config(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel("Step 3: Emulator Configuration")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        layout.addWidget(title)

        # Basic Group
        basic_group = QGroupBox("Basic Settings")
        basic_group.setStyleSheet("QGroupBox { font-weight: 600; font-size: 12px; }")
        b_layout = QVBoxLayout(basic_group)
        b_layout.setSpacing(8)

        name_row = QHBoxLayout()
        name_lbl = QLabel("AVD Name:")
        name_lbl.setFixedWidth(110)
        self._name_input = QLineEdit()
        name_row.addWidget(name_lbl)
        name_row.addWidget(self._name_input, 1)
        b_layout.addLayout(name_row)

        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("font-size: 11px; color: #8b8e94;")
        b_layout.addWidget(self._summary_label)

        layout.addWidget(basic_group)

        # Advanced Group
        adv_group = QGroupBox("Advanced Hardware Settings (Optional)")
        adv_group.setStyleSheet("QGroupBox { font-weight: 600; font-size: 12px; }")
        a_layout = QVBoxLayout(adv_group)
        a_layout.setSpacing(8)

        # RAM
        ram_row = QHBoxLayout()
        ram_lbl = QLabel("RAM (MB):")
        ram_lbl.setFixedWidth(110)
        self._ram_spin = QSpinBox()
        self._ram_spin.setRange(1024, 16384)
        self._ram_spin.setSingleStep(512)
        self._ram_spin.setValue(4096)
        ram_row.addWidget(ram_lbl)
        ram_row.addWidget(self._ram_spin)
        ram_row.addStretch(1)
        a_layout.addLayout(ram_row)

        # Storage
        storage_row = QHBoxLayout()
        storage_lbl = QLabel("Storage (MB):")
        storage_lbl.setFixedWidth(110)
        self._storage_spin = QSpinBox()
        self._storage_spin.setRange(2048, 65536)
        self._storage_spin.setSingleStep(1024)
        self._storage_spin.setValue(6144)
        storage_row.addWidget(storage_lbl)
        storage_row.addWidget(self._storage_spin)
        storage_row.addStretch(1)
        a_layout.addLayout(storage_row)

        # SD Card
        sd_row = QHBoxLayout()
        sd_lbl = QLabel("SD Card (MB):")
        sd_lbl.setFixedWidth(110)
        self._sd_spin = QSpinBox()
        self._sd_spin.setRange(0, 16384)
        self._sd_spin.setSingleStep(256)
        self._sd_spin.setValue(512)
        sd_row.addWidget(sd_lbl)
        sd_row.addWidget(self._sd_spin)
        sd_row.addStretch(1)
        a_layout.addLayout(sd_row)

        layout.addWidget(adv_group)
        layout.addStretch(1)
        return page

    # -------------------------------------------------------------------------
    # Step 4: Creation & Progress
    # -------------------------------------------------------------------------
    def _build_step4_progress(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self._status_heading = QLabel("Creating Android Virtual Device...")
        self._status_heading.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        layout.addWidget(self._status_heading)

        self._status_msg = QLabel("Initializing configuration...")
        self._status_msg.setStyleSheet("font-size: 12px; color: #9ca3af;")
        self._status_msg.setWordWrap(True)
        layout.addWidget(self._status_msg)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # Indeterminate initially
        self._progress_bar.setStyleSheet(
            """
            QProgressBar {
                background-color: #212226;
                border: 1px solid #35373e;
                border-radius: 4px;
                text-align: center;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
            }
            """
        )
        layout.addWidget(self._progress_bar)

        self._details_box = QLabel()
        self._details_box.setStyleSheet("font-family: monospace; font-size: 11px; color: #8b8e94;")
        self._details_box.setWordWrap(True)
        layout.addWidget(self._details_box)

        layout.addStretch(1)
        return page

    # -------------------------------------------------------------------------
    # Footer Navigation
    # -------------------------------------------------------------------------
    def _build_footer(self) -> QWidget:
        footer = QWidget()
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.setSpacing(10)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid #35373e; color: #9ca3af; "
            "border-radius: 4px; padding: 7px 16px; font-size: 12px; }"
            "QPushButton:hover { color: #ffffff; background: #212226; }"
        )
        self._cancel_btn.clicked.connect(self.reject)
        f_layout.addWidget(self._cancel_btn)

        f_layout.addStretch(1)

        self._back_btn = QPushButton("Back")
        self._back_btn.setStyleSheet(
            "QPushButton { background: #212226; border: 1px solid #35373e; color: #e5e7eb; "
            "border-radius: 4px; padding: 7px 16px; font-size: 12px; }"
            "QPushButton:hover { background: #2a2c31; }"
        )
        self._back_btn.clicked.connect(self._on_back_clicked)
        f_layout.addWidget(self._back_btn)

        self._next_btn = QPushButton("Next")
        self._next_btn.setStyleSheet(
            "QPushButton { background: #2563eb; border: 1px solid #3b82f6; color: #ffffff; "
            "border-radius: 4px; padding: 7px 20px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #1d4ed8; }"
        )
        self._next_btn.clicked.connect(self._on_next_clicked)
        f_layout.addWidget(self._next_btn)

        return footer

    # -------------------------------------------------------------------------
    # Wizard Navigation Flow
    # -------------------------------------------------------------------------
    def _update_step_view(self) -> None:
        self._stack.setCurrentIndex(self._current_step)

        # Update step labels
        for idx, lbl in enumerate(self._step_labels):
            if idx == self._current_step:
                lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #3b82f6;")
            elif idx < self._current_step:
                lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #10b981;")
            else:
                lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #6b7280;")

        self._back_btn.setEnabled(self._current_step > 0 and self._current_step < 3)

        if self._current_step == 2:
            self._next_btn.setText("Create Emulator")
            # Populate auto-name if empty
            if self._selected_profile and self._selected_image:
                prof_name = re.sub(r"\W+", "_", self._selected_profile.name)
                def_name = f"{prof_name}_API_{self._selected_image.api_level}"
                self._name_input.setText(def_name)
                prof_summary = f"{self._selected_profile.name} ({self._selected_profile.oem})"
                ver_summary = (
                    f"{self._selected_image.android_version} "
                    f"(API {self._selected_image.api_level})"
                )
                tag_summary = (
                    f"{self._selected_image.display_tag} "
                    f"({self._selected_image.abi})"
                )
                self._summary_label.setText(
                    f"Profile: {prof_summary} | Version: {ver_summary} | Tag: {tag_summary}"
                )
        elif self._current_step == 3:
            self._back_btn.setVisible(False)
            self._next_btn.setVisible(False)
            self._cancel_btn.setText("Close")
            self._start_creation_process()
        else:
            self._next_btn.setText("Next")

        self._update_next_button_state()

    def _update_next_button_state(self) -> None:
        if self._current_step == 0:
            self._next_btn.setEnabled(self._selected_profile is not None)
        elif self._current_step == 1:
            self._next_btn.setEnabled(self._selected_image is not None)
        else:
            self._next_btn.setEnabled(True)

    def _on_next_clicked(self) -> None:
        if self._current_step < 3:
            self._current_step += 1
            self._update_step_view()

    def _on_back_clicked(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            self._update_step_view()

    # -------------------------------------------------------------------------
    # Creation Process
    # -------------------------------------------------------------------------
    def _start_creation_process(self) -> None:
        if not self._selected_profile or not self._selected_image:
            return

        avd_name = self._name_input.text().strip()
        if not avd_name:
            QMessageBox.warning(self, "Invalid Name", "Please provide a valid AVD name.")
            self._current_step = 2
            self._update_step_view()
            return

        # Check if system image is already installed
        if self._selected_image.is_installed:
            self._status_heading.setText("Creating Virtual Device...")
            self._status_msg.setText(
                f"Creating AVD '{avd_name}' with system image {self._selected_image.path}..."
            )
            self._execute_avd_creation(avd_name)
        else:
            # Missing image -> download first
            self._status_heading.setText("Downloading System Image...")
            self._status_msg.setText(
                f"The system image '{self._selected_image.path}' must be downloaded via "
                "Android SDK Manager before creating the virtual device."
            )
            self._progress_bar.setRange(0, 0)
            self._download_worker = self._sim_mgr.create_download_thread(
                self._selected_image.path, parent=self
            )
            self._download_worker.progress.connect(self._on_download_progress)
            self._download_worker.finished_success.connect(
                lambda pkg: self._on_download_success(avd_name)
            )
            self._download_worker.failed.connect(self._on_creation_failed)
            self._download_worker.start()

    def _on_download_progress(self, msg: str) -> None:
        self._details_box.setText(msg)

    def _on_download_success(self, avd_name: str) -> None:
        self._status_heading.setText("System Image Downloaded. Creating Virtual Device...")
        self._execute_avd_creation(avd_name)

    def _execute_avd_creation(self, avd_name: str) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.processEvents()

        success, msg = self._avd_mgr.create_avd(
            name=avd_name,
            system_image_path=self._selected_image.path,
            device_profile_id=self._selected_profile.id,
            ram_mb=self._ram_spin.value(),
            sdcard_size_mb=self._sd_spin.value(),
            storage_mb=self._storage_spin.value(),
        )

        self._progress_bar.setRange(0, 100)
        if success:
            self._progress_bar.setValue(100)
            self._status_heading.setText("Emulator Created Successfully!")
            self._status_heading.setStyleSheet("font-size: 16px; font-weight: 700; color: #10b981;")
            self._status_msg.setText(
                f"Virtual device '{avd_name}' is ready. "
                "It will appear in Device Manager immediately."
            )
            self._cancel_btn.setText("Finish")
            self._cancel_btn.setStyleSheet(
                "QPushButton { background: #2563eb; border: 1px solid #3b82f6; color: #ffffff; "
                "border-radius: 4px; padding: 7px 20px; font-weight: 600; }"
            )
            self.emulator_created.emit(avd_name)
        else:
            self._on_creation_failed(msg)

    def _on_creation_failed(self, error_msg: str) -> None:
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._status_heading.setText("Failed to Create Emulator")
        self._status_heading.setStyleSheet("font-size: 16px; font-weight: 700; color: #ef4444;")
        self._status_msg.setText(f"Error:\n{error_msg}")
        self._details_box.setText(
            "Possible causes:\n"
            "- AVD Manager is missing or JAVA_HOME is not set.\n"
            "- Another virtual device already exists with this name.\n"
            "- Insufficient disk space or permission denied."
        )
        self._cancel_btn.setText("Close")
