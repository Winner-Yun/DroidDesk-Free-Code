"""Unified Device & Emulator Manager page for DroidDesk.

Manages physical Android devices (connected via ADB / Wi-Fi) and virtual
Android devices (managed through Android SDK / AVD / Emulator).
"""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from droiddesk.android.models import AndroidEnvStatus
from droiddesk.android.system_image_manager import SystemImageManager
from droiddesk.context import AppContext
from droiddesk.device.models import ManagedDevice
from droiddesk.services.device_service import DeviceService
from droiddesk.ui.dialogs.android_environment_dialog import AndroidEnvironmentDialog
from droiddesk.ui.dialogs.apk_action_dialog import ApkActionDialog
from droiddesk.ui.dialogs.create_emulator_wizard import CreateEmulatorWizard
from droiddesk.ui.dialogs.device_logs_dialog import DeviceLogsDialog
from droiddesk.ui.dialogs.screenshot_dialog import ScreenshotViewerDialog
from droiddesk.ui.theme import TEXT_MUTED, get_icon
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.status_pill import StatusDot, TagPill


class _EnvCheckWorker(QThread):
    status_ready = Signal(object)

    def __init__(self, dev_service: DeviceService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._dev_service = dev_service

    def run(self) -> None:
        try:
            status = self._dev_service.check_environment(force=True)
            self.status_ready.emit(status)
        except Exception:
            pass


class DevicesPage(QWidget):
    open_logcat_requested = Signal(str)
    open_screen_requested = Signal(str)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._dev_service = ctx.device_service
        self._selected_device_id: str | None = None
        self._last_rendered_signature: tuple[object, ...] | None = None
        self._env_worker: _EnvCheckWorker | None = None
        self.setProperty("role", "page")

        self._sim_manager = SystemImageManager(
            tool_locator=self._ctx.tool_locator,
            runner=self._dev_service.avd_manager._runner,
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # Header with actions
        header = PageHeader(
            "Device & Emulator Manager",
            "Manage physical Android phones and Android SDK virtual emulators in one place.",
        )

        # Environment status pill
        self._env_btn = QPushButton("Checking SDK...")
        self._env_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._env_btn.setIcon(get_icon("settings", size=13, color=TEXT_MUTED))
        self._env_btn.setIconSize(QSize(13, 13))
        self._env_btn.clicked.connect(self._on_open_env_dialog)
        header.add_action(self._env_btn)

        # Create Emulator button
        self._create_emu_btn = QPushButton("+ Create Emulator")
        self._create_emu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_emu_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; border: 1px solid #3b82f6; color: #ffffff; "
            "border-radius: 4px; padding: 6px 14px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
        )
        self._create_emu_btn.clicked.connect(self._on_create_emulator_clicked)
        header.add_action(self._create_emu_btn)

        # Wi-Fi input and button
        self._wifi_input = QLineEdit("192.168.1.24:5555")
        self._wifi_input.setFixedWidth(160)
        self._wifi_btn = QPushButton("Connect Wi-Fi")
        self._wifi_btn.setIcon(get_icon("wifi", size=13, color=TEXT_MUTED))
        self._wifi_btn.setIconSize(QSize(13, 13))
        self._wifi_btn.clicked.connect(self._on_connect_wifi_clicked)
        header.add_action(self._wifi_input)
        header.add_action(self._wifi_btn)

        # Refresh button
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setIcon(get_icon("rotate-cw", size=13, color=TEXT_MUTED))
        self._refresh_btn.setIconSize(QSize(13, 13))
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        header.add_action(self._refresh_btn)
        outer.addWidget(header)

        # Environment Warning Banner (hidden if ready)
        self._env_banner = self._build_env_banner()
        outer.addWidget(self._env_banner)

        # Main Layout: Left Device List (Scrollable), Right Details Sidebar
        self._content_row = QHBoxLayout()
        self._content_row.setSpacing(16)

        # Left Scroll Area containing Physical & Virtual sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        scroll_widget = QWidget()
        self._devices_list_layout = QVBoxLayout(scroll_widget)
        self._devices_list_layout.setContentsMargins(0, 0, 0, 0)
        self._devices_list_layout.setSpacing(20)

        # 1. Physical Devices Container
        self._physical_container = QWidget()
        self._physical_layout = QVBoxLayout(self._physical_container)
        self._physical_layout.setContentsMargins(0, 0, 0, 0)
        self._physical_layout.setSpacing(10)
        self._devices_list_layout.addWidget(self._physical_container)

        # 2. Virtual Devices Container
        self._virtual_container = QWidget()
        self._virtual_layout = QVBoxLayout(self._virtual_container)
        self._virtual_layout.setContentsMargins(0, 0, 0, 0)
        self._virtual_layout.setSpacing(10)
        self._devices_list_layout.addWidget(self._virtual_container)

        self._devices_list_layout.addStretch(1)
        scroll.setWidget(scroll_widget)
        self._content_row.addWidget(scroll, 1)

        # Right Device Details Drawer
        self._detail_panel = self._empty_detail()
        self._detail_panel.setFixedWidth(320)
        self._content_row.addWidget(self._detail_panel)

        outer.addLayout(self._content_row, 1)

        # Connect signals
        self._dev_service.managed_devices_changed.connect(self._repopulate)
        self._dev_service.emulator_manager.state_changed.connect(lambda *_: self._refresh_lists())
        self._dev_service.emulator_manager.emulator_start_failed.connect(
            self._on_emulator_start_failed
        )

        self._check_environment_status(force=False, async_check=True)
        self._repopulate(self._dev_service.managed_devices())

    # -------------------------------------------------------------------------
    # Environment Status Banner & Checks
    # -------------------------------------------------------------------------
    def _build_env_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("envBanner")
        banner.setStyleSheet(
            "background-color: #3b200b; border: 1px solid #78350f; "
            "border-radius: 6px; padding: 10px;"
        )
        b_layout = QHBoxLayout(banner)
        b_layout.setContentsMargins(12, 6, 12, 6)
        b_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("alert-triangle", size=18, color="#f59e0b").pixmap(18, 18))
        b_layout.addWidget(icon_lbl)

        self._banner_msg = QLabel("Android development environment requires configuration.")
        self._banner_msg.setStyleSheet("color: #fde68a; font-size: 12px; font-weight: 500;")
        b_layout.addWidget(self._banner_msg, 1)

        setup_btn = QPushButton("Setup Android Tools")
        setup_btn.setStyleSheet(
            "QPushButton { background: #d97706; color: #ffffff; font-weight: 600; "
            "border-radius: 4px; padding: 5px 12px; font-size: 11px; }"
            "QPushButton:hover { background: #b45309; }"
        )
        setup_btn.clicked.connect(self._on_open_env_dialog)
        b_layout.addWidget(setup_btn)

        banner.setVisible(False)
        return banner

    def _check_environment_status(self, force: bool = False, async_check: bool = False) -> None:
        if async_check:
            cached = self._dev_service.get_cached_environment()
            if cached is not None:
                self._apply_env_status(cached)
            self._start_async_env_check()
            return

        status: AndroidEnvStatus = self._dev_service.check_environment(force=force)
        self._apply_env_status(status)

    def _start_async_env_check(self) -> None:
        if self._env_worker is not None and self._env_worker.isRunning():
            return
        self._env_worker = _EnvCheckWorker(self._dev_service, self)
        self._env_worker.status_ready.connect(self._apply_env_status)
        self._env_worker.start()

    def _apply_env_status(self, status: AndroidEnvStatus) -> None:
        if status.is_ready:
            self._env_btn.setIcon(get_icon("check-circle-2", size=13, color="#34d399"))
            self._env_btn.setText("Android SDK Ready")
            self._env_btn.setStyleSheet("color: #34d399; font-weight: 600;")
            self._env_banner.setVisible(False)
        else:
            self._env_btn.setIcon(get_icon("alert-triangle", size=13, color="#fbbf24"))
            self._env_btn.setText(status.state.value.replace("_", " "))
            self._env_btn.setStyleSheet("color: #fbbf24; font-weight: 600;")
            self._banner_msg.setText(
                status.error_message
                or "Android SDK tools require configuration to enable full features."
            )
            self._env_banner.setVisible(True)

    def _on_open_env_dialog(self) -> None:
        dlg = AndroidEnvironmentDialog(
            sdk_manager=self._dev_service.sdk_manager,
            system_image_manager=self._sim_manager,
            parent=self,
        )
        dlg.exec()
        self._check_environment_status(force=True, async_check=True)
        self._dev_service.refresh()

    def _on_create_emulator_clicked(self) -> None:
        wizard = CreateEmulatorWizard(
            avd_manager=self._dev_service.avd_manager,
            system_image_manager=self._sim_manager,
            tool_locator=self._ctx.tool_locator,
            parent=self,
        )
        wizard.emulator_created.connect(lambda avd_name: self._dev_service.refresh())
        wizard.exec()

    # -------------------------------------------------------------------------
    # Devices List Rendering
    # -------------------------------------------------------------------------
    def _refresh_lists(self) -> None:
        self._last_rendered_signature = None
        self._repopulate(self._dev_service.managed_devices())

    def _repopulate(self, devices: list[ManagedDevice]) -> None:
        signature = tuple(
            (d.id, d.status, d.serial, d.battery_level, d.error_message) for d in devices
        )
        if signature == self._last_rendered_signature:
            return
        self._last_rendered_signature = signature

        # Clear previous widgets
        self._clear_layout(self._physical_layout)
        self._clear_layout(self._virtual_layout)

        phys_devices = [d for d in devices if d.is_physical]
        virt_devices = [d for d in devices if d.is_virtual]

        # 1. Render Physical Devices Section
        p_hdr = self._section_header(
            "Physical Devices",
            f"{len(phys_devices)} connected",
            "smartphone",
            None,
        )
        self._physical_layout.addWidget(p_hdr)

        if not phys_devices:
            empty_phys = Card()
            e_layout = empty_phys.body_layout()
            e_lbl = QLabel(
                "No physical Android device connected via USB or Wi-Fi.<br>"
                "<span style='font-size: 11px; color: #8b8e94;'>"
                "Connect your phone via USB and enable "
                "<b>USB Debugging</b> in Developer Options.</span>"
            )
            e_lbl.setWordWrap(True)
            e_layout.addWidget(e_lbl)
            self._physical_layout.addWidget(empty_phys)
        else:
            for dev in phys_devices:
                self._physical_layout.addWidget(self._build_physical_device_card(dev))

        # 2. Render Virtual Devices Section
        v_hdr = self._section_header(
            "Virtual Devices (Emulators)",
            f"{len(virt_devices)} configured",
            "bot",
            ("+ Create Emulator", self._on_create_emulator_clicked),
        )
        self._virtual_layout.addWidget(v_hdr)

        if not virt_devices:
            empty_virt = Card()
            e_layout = empty_virt.body_layout()
            e_lbl = QLabel(
                "No Android Virtual Devices (AVDs) found on this machine.<br>"
                "<span style='font-size: 11px; color: #8b8e94;'>"
                "Click <b>+ Create Emulator</b> to set up an official Android emulator.</span>"
            )
            e_lbl.setWordWrap(True)
            e_layout.addWidget(e_lbl)
            self._virtual_layout.addWidget(empty_virt)
        else:
            for dev in virt_devices:
                self._virtual_layout.addWidget(self._build_virtual_device_card(dev))

        # Restore selection
        selected = self._dev_service.discovery_service.get_device(self._selected_device_id or "")
        if selected:
            self._swap_detail(self._build_detail(selected))
        elif devices:
            self._selected_device_id = devices[0].id
            self._swap_detail(self._build_detail(devices[0]))
        else:
            self._swap_detail(self._empty_detail())

    def _section_header(
        self,
        title: str,
        subtitle: str,
        icon_name: str,
        action: tuple[str, object] | None,
    ) -> QWidget:
        header = QWidget()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 4, 0, 4)
        h_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon(icon_name, size=18, color="#3b82f6").pixmap(18, 18))
        h_layout.addWidget(icon_lbl)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        h_layout.addWidget(t_lbl)

        sub_lbl = QLabel(f"({subtitle})")
        sub_lbl.setStyleSheet("font-size: 12px; color: #8b8e94;")
        h_layout.addWidget(sub_lbl)

        h_layout.addStretch(1)

        if action:
            btn_text, btn_handler = action
            btn = QPushButton(btn_text)
            btn.setStyleSheet(
                "QPushButton { background: #212226; border: 1px solid #35373e; color: #e5e7eb; "
                "border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 600; }"
                "QPushButton:hover { background: #2a2c31; border-color: #3b82f6; color: #ffffff; }"
            )
            btn.clicked.connect(btn_handler)
            h_layout.addWidget(btn)

        return header

    # -------------------------------------------------------------------------
    # Physical Device Card
    # -------------------------------------------------------------------------
    def _build_physical_device_card(self, dev: ManagedDevice) -> Card:
        card = Card()
        layout = card.body_layout()
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Top Info Row
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # Status dot
        status_key = (
            "active"
            if dev.status == "Ready"
            else "unauthorized"
            if dev.status == "Unauthorized"
            else "offline"
        )
        top_row.addWidget(StatusDot(status_key))

        title_lbl = QLabel(dev.name)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        top_row.addWidget(title_lbl)

        serial_lbl = QLabel(f"({dev.serial or 'No serial'})")
        serial_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #38bdf8;")
        top_row.addWidget(serial_lbl)

        top_row.addStretch(1)

        top_row.addWidget(TagPill(dev.status))
        top_row.addWidget(TagPill(dev.link_type))
        layout.addLayout(top_row)

        # Meta properties row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(16)
        meta_parts = []
        if dev.android_version:
            meta_parts.append(f"Android {dev.android_version}")
        if dev.api_level:
            meta_parts.append(f"API {dev.api_level}")
        if dev.abi:
            meta_parts.append(dev.abi)
        if dev.battery_level is not None:
            meta_parts.append(f"Battery: {dev.battery_level}%")

        meta_lbl = QLabel(" • ".join(meta_parts) if meta_parts else "Physical Device")
        meta_lbl.setStyleSheet("font-size: 12px; color: #9ca3af;")
        meta_row.addWidget(meta_lbl)
        meta_row.addStretch(1)
        layout.addLayout(meta_row)

        # Unauthorized warning message if applicable
        if dev.status == "Unauthorized":
            warn_box = QFrame()
            warn_box.setStyleSheet("background-color: #3b200b; border-radius: 4px; padding: 6px;")
            w_layout = QHBoxLayout(warn_box)
            w_layout.setContentsMargins(8, 4, 8, 4)
            w_msg = QLabel("<b>Device unauthorized.</b> Unlock your phone and allow USB debugging.")
            w_msg.setStyleSheet("color: #fde68a; font-size: 11px;")
            w_layout.addWidget(w_msg)
            layout.addWidget(warn_box)

        # Actions Row
        act_row = QHBoxLayout()
        act_row.setSpacing(8)

        if dev.can_screen_mirror:
            screen_btn = QPushButton("Screen")
            screen_btn.setIcon(get_icon("cast", size=12, color="#9ca3af"))
            screen_btn.clicked.connect(
                lambda _=None, s=dev.serial: self.open_screen_requested.emit(s)
            )
            act_row.addWidget(screen_btn)

        if dev.can_install_apk:
            apk_btn = QPushButton("APK")
            apk_btn.setIcon(get_icon("box", size=12, color="#9ca3af"))
            apk_btn.clicked.connect(lambda _=None, d=dev: self._open_apk_dialog(d))
            act_row.addWidget(apk_btn)

        if dev.can_view_logs:
            logs_btn = QPushButton("Logs")
            logs_btn.setIcon(get_icon("scroll-text", size=12, color="#9ca3af"))
            logs_btn.clicked.connect(lambda _=None, d=dev: self._open_logs_dialog(d))
            act_row.addWidget(logs_btn)

        if dev.status in ("Offline", "Unauthorized"):
            recon_btn = QPushButton("Reconnect")
            recon_btn.setIcon(get_icon("rotate-cw", size=12, color="#9ca3af"))
            recon_btn.clicked.connect(lambda _=None, s=dev.serial: self._dev_service.reconnect(s))
            act_row.addWidget(recon_btn)

        act_row.addStretch(1)

        details_btn = QPushButton("Details")
        details_btn.setIcon(get_icon("info", size=12, color="#9ca3af"))
        details_btn.clicked.connect(lambda _=None, d=dev: self._select_device(d))
        act_row.addWidget(details_btn)

        layout.addLayout(act_row)
        return card

    # -------------------------------------------------------------------------
    # Virtual Device Card
    # -------------------------------------------------------------------------
    def _build_virtual_device_card(self, dev: ManagedDevice) -> Card:
        card = Card()
        layout = card.body_layout()
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Top Info Row
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        status_low = dev.status.lower()
        if status_low == "running":
            top_row.addWidget(StatusDot("active"))
        elif status_low in ("starting", "booting"):
            top_row.addWidget(StatusDot("ready"))
        elif status_low == "error":
            top_row.addWidget(StatusDot("offline"))
        else:
            top_row.addWidget(StatusDot("offline"))

        title_lbl = QLabel(dev.name)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")
        top_row.addWidget(title_lbl)

        if dev.serial:
            serial_lbl = QLabel(f"({dev.serial})")
            serial_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #38bdf8;")
            top_row.addWidget(serial_lbl)

        top_row.addStretch(1)

        # Status Pill
        top_row.addWidget(TagPill(dev.status))
        top_row.addWidget(TagPill("Virtual"))
        layout.addLayout(top_row)

        # Meta properties row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(16)
        meta_parts = []
        if dev.android_version:
            meta_parts.append(dev.android_version)
        if dev.abi:
            meta_parts.append(dev.abi)
        if dev.model:
            meta_parts.append(dev.model)

        meta_lbl = QLabel(" • ".join(meta_parts) if meta_parts else "Android Emulator")
        meta_lbl.setStyleSheet("font-size: 12px; color: #9ca3af;")
        meta_row.addWidget(meta_lbl)
        meta_row.addStretch(1)
        layout.addLayout(meta_row)

        # Error message warning if applicable
        if dev.error_message:
            err_box = QFrame()
            err_box.setStyleSheet("background-color: #3b0d0d; border-radius: 4px; padding: 6px;")
            e_layout = QHBoxLayout(err_box)
            e_layout.setContentsMargins(8, 4, 8, 4)
            e_msg = QLabel(f"<b>Notice:</b> {dev.error_message}")
            e_msg.setStyleSheet("color: #fca5a5; font-size: 11px;")
            e_layout.addWidget(e_msg)
            layout.addWidget(err_box)

        # Actions Row
        act_row = QHBoxLayout()
        act_row.setSpacing(8)

        avd_name = dev.avd_name or ""

        if status_low in ("stopped", "error"):
            start_text = "Start" if status_low == "stopped" else "Retry"
            start_btn = QPushButton(start_text)
            start_btn.setIcon(get_icon("play", size=12, color="#10b981"))
            start_btn.setStyleSheet(
                "QPushButton { background: #064e3b; border: 1px solid #059669; color: #ffffff; "
                "border-radius: 4px; padding: 5px 14px; font-weight: 600; }"
                "QPushButton:hover { background: #047857; }"
            )
            start_btn.clicked.connect(
                lambda _=None, n=avd_name, b=start_btn: self._on_start_emulator(n, b)
            )
            act_row.addWidget(start_btn)

            if status_low == "error":
                release_btn = QPushButton("Release Locks")
                release_btn.setIcon(get_icon("rotate-cw", size=12, color="#38bdf8"))
                release_btn.clicked.connect(
                    lambda _=None, n=avd_name: self._on_force_release_locks(n)
                )
                act_row.addWidget(release_btn)

            del_btn = QPushButton("Delete")
            del_btn.setIcon(get_icon("trash-2", size=12, color="#ef4444"))
            del_btn.setProperty("role", "danger")
            del_btn.clicked.connect(lambda _=None, d=dev: self._on_delete_emulator(d))
            act_row.addWidget(del_btn)

        elif status_low in ("starting", "booting"):
            boot_lbl = QPushButton(f"{dev.status}...")
            boot_lbl.setIcon(get_icon("loader-2", size=12, color="#f59e0b"))
            boot_lbl.setEnabled(False)
            act_row.addWidget(boot_lbl)

            stop_btn = QPushButton("Stop")
            stop_btn.setIcon(get_icon("square", size=12, color="#ef4444"))
            stop_btn.clicked.connect(lambda _=None, n=avd_name: self._dev_service.stop_emulator(n))
            act_row.addWidget(stop_btn)

            del_btn = QPushButton("Delete")
            del_btn.setIcon(get_icon("trash-2", size=12, color="#ef4444"))
            del_btn.setProperty("role", "danger")
            del_btn.clicked.connect(lambda _=None, d=dev: self._on_delete_emulator(d))
            act_row.addWidget(del_btn)

        elif status_low == "running":
            if dev.can_screen_mirror:
                screen_btn = QPushButton("Screen")
                screen_btn.setIcon(get_icon("cast", size=12, color="#9ca3af"))
                screen_btn.clicked.connect(
                    lambda _=None, s=dev.serial: self.open_screen_requested.emit(s)
                )
                act_row.addWidget(screen_btn)

            apk_btn = QPushButton("APK")
            apk_btn.setIcon(get_icon("box", size=12, color="#9ca3af"))
            apk_btn.clicked.connect(lambda _=None, d=dev: self._open_apk_dialog(d))
            act_row.addWidget(apk_btn)

            logs_btn = QPushButton("Logs")
            logs_btn.setIcon(get_icon("scroll-text", size=12, color="#9ca3af"))
            logs_btn.clicked.connect(lambda _=None, d=dev: self._open_logs_dialog(d))
            act_row.addWidget(logs_btn)

            restart_btn = QPushButton("Restart")
            restart_btn.setIcon(get_icon("rotate-cw", size=12, color="#9ca3af"))
            restart_btn.clicked.connect(
                lambda _=None, n=avd_name: self._dev_service.restart_emulator(n)
            )
            act_row.addWidget(restart_btn)

            stop_btn = QPushButton("Stop")
            stop_btn.setIcon(get_icon("square", size=12, color="#ef4444"))
            stop_btn.clicked.connect(lambda _=None, n=avd_name: self._dev_service.stop_emulator(n))
            act_row.addWidget(stop_btn)

            del_btn = QPushButton("Delete")
            del_btn.setIcon(get_icon("trash-2", size=12, color="#ef4444"))
            del_btn.setProperty("role", "danger")
            del_btn.clicked.connect(lambda _=None, d=dev: self._on_delete_emulator(d))
            act_row.addWidget(del_btn)

        act_row.addStretch(1)

        details_btn = QPushButton("Details")
        details_btn.setIcon(get_icon("info", size=12, color="#9ca3af"))
        details_btn.clicked.connect(lambda _=None, d=dev: self._select_device(d))
        act_row.addWidget(details_btn)

        layout.addLayout(act_row)
        return card

    # -------------------------------------------------------------------------
    # Emulator Lifecycle Handlers
    # -------------------------------------------------------------------------
    def _on_start_emulator(self, avd_name: str, button: QPushButton | None = None) -> None:
        dev = self._dev_service.discovery_service.get_device(f"virtual:{avd_name}")
        if dev and dev.error_message:
            QMessageBox.warning(
                self,
                "Cannot Start Emulator",
                f"Cannot launch emulator '<b>{dev.name}</b>':\n\n"
                f"{dev.error_message}\n\n"
                f"The required Android system image is missing or not installed.",
            )
            return

        if button:
            button.setEnabled(False)
            button.setText("Starting...")
        self._dev_service.start_emulator(avd_name)

    def _on_force_release_locks(self, avd_name: str) -> None:
        success, msg = self._dev_service.force_release_emulator_locks(avd_name)
        if success:
            QMessageBox.information(self, "Locks Released", msg)
        else:
            QMessageBox.warning(self, "Release Failed", msg)

    def _on_emulator_start_failed(self, avd_name: str, title: str, details: str) -> None:
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Unable to Start Emulator")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText(f"<b>{title}</b>")
        msg_box.setInformativeText(details)

        retry_btn = msg_box.addButton(
            "Release Locks and Retry", QMessageBox.ButtonRole.ActionRole
        )
        msg_box.addButton(QMessageBox.StandardButton.Close)

        msg_box.exec()

        if msg_box.clickedButton() == retry_btn:
            self._dev_service.force_release_emulator_locks(avd_name)
            self._dev_service.start_emulator(avd_name)

    def _on_delete_emulator(self, dev: ManagedDevice) -> None:
        avd_name = dev.avd_name or dev.name
        is_active = dev.is_online or dev.status.lower() in ("running", "booting", "starting")

        if is_active:
            msg = (
                f"Are you sure you want to delete the emulator:\n\n"
                f"  {dev.name}\n\n"
                f"This emulator is currently active ({dev.status}).\n"
                f"Deleting it will stop the running process and permanently remove "
                f"its virtual configuration.\n\n"
                f"The underlying Android system image will remain intact.\n\n"
                f"Do you want to proceed?"
            )
        else:
            msg = (
                f"Are you sure you want to delete the emulator:\n\n"
                f"  {dev.name}\n\n"
                f"This removes the virtual device configuration.\n"
                f"The underlying Android system image will remain installed."
            )

        reply = QMessageBox.question(
            self,
            "Delete Emulator?",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if is_active:
                self._dev_service.force_release_emulator_locks(avd_name)
            success, msg_text = self._dev_service.delete_emulator(avd_name)
            if success:
                if self._selected_device_id == dev.id:
                    self._selected_device_id = None
                    self._swap_detail(self._build_empty_detail())
                QMessageBox.information(self, "Emulator Deleted", msg_text)
            else:
                QMessageBox.warning(self, "Delete Failed", msg_text)

    # -------------------------------------------------------------------------
    # Dialog Openers
    # -------------------------------------------------------------------------
    def _open_apk_dialog(self, dev: ManagedDevice) -> None:
        dlg = ApkActionDialog(
            apk_manager=self._dev_service.apk_manager,
            devices=self._dev_service.managed_devices(),
            initial_device=dev,
            initial_apk_path=None,
            parent=self,
        )
        dlg.exec()

    def _open_logs_dialog(self, dev: ManagedDevice) -> None:
        if not dev.serial:
            QMessageBox.warning(
                self, "Device Offline", "Device must be connected and running to view logs."
            )
            return
        dlg = DeviceLogsDialog(
            serial=dev.serial,
            device_name=dev.name,
            adb_client=self._dev_service.adb_client,
            parent=self,
        )
        dlg.exec()

    def _select_device(self, dev: ManagedDevice) -> None:
        self._selected_device_id = dev.id
        self._swap_detail(self._build_detail(dev))

    # -------------------------------------------------------------------------
    # Device Details Sidebar
    # -------------------------------------------------------------------------
    def _empty_detail(self) -> QWidget:
        card = Card()
        layout = card.body_layout()
        lbl = QLabel("No device selected")
        lbl.setProperty("role", "muted")
        layout.addWidget(lbl)
        layout.addStretch(1)
        return card

    def _build_detail(self, dev: ManagedDevice) -> QWidget:
        card = Card()
        layout = card.body_layout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("DEVICE DETAILS")
        heading.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #6b7280; letter-spacing: 1px;"
        )
        layout.addWidget(heading)

        name_lbl = QLabel(dev.name)
        name_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        layout.addWidget(name_lbl)

        pills_row = QHBoxLayout()
        pills_row.addWidget(TagPill(dev.status))
        pills_row.addWidget(TagPill(dev.device_type.value.capitalize()))
        pills_row.addStretch(1)
        layout.addLayout(pills_row)

        layout.addWidget(self._section_label("PROPERTIES"))

        props = [
            ("Type", dev.device_type.value.capitalize()),
            ("Status", dev.status),
            ("Serial", dev.serial or "-"),
            ("Model", dev.model or "-"),
            ("Manufacturer", dev.manufacturer or "-"),
            ("Android", dev.android_version or "-"),
            ("API Level", str(dev.api_level) if dev.api_level else "-"),
            ("CPU ABI", dev.abi or "-"),
            ("Density", f"{dev.density} dpi" if dev.density else "-"),
            ("Connection", dev.link_type),
        ]
        if dev.battery_level is not None:
            props.append(("Battery", f"{dev.battery_level}%"))
        if dev.screen_size:
            props.append(("Resolution", f"{dev.screen_size[0]}x{dev.screen_size[1]}"))

        for label, val in props:
            layout.addLayout(self._property_row(label, val))

        layout.addStretch(1)

        # Quick Actions in Sidebar
        if dev.is_online and dev.serial:
            layout.addWidget(self._section_label("ACTIONS"))

            screen_btn = QPushButton("Share Screen")
            screen_btn.setIcon(get_icon("cast", size=13, color=TEXT_MUTED))
            screen_btn.setIconSize(QSize(13, 13))
            screen_btn.clicked.connect(lambda: self.open_screen_requested.emit(dev.serial))
            layout.addWidget(screen_btn)

            apk_btn = QPushButton("Install APK")
            apk_btn.setIcon(get_icon("box", size=13, color=TEXT_MUTED))
            apk_btn.setIconSize(QSize(13, 13))
            apk_btn.clicked.connect(lambda: self._open_apk_dialog(dev))
            layout.addWidget(apk_btn)

            logs_btn = QPushButton("Open Logcat")
            logs_btn.setIcon(get_icon("scroll-text", size=13, color=TEXT_MUTED))
            logs_btn.setIconSize(QSize(13, 13))
            logs_btn.clicked.connect(lambda: self._open_logs_dialog(dev))
            layout.addWidget(logs_btn)

            shot_btn = QPushButton("Take Screenshot")
            shot_btn.setIcon(get_icon("camera", size=13, color=TEXT_MUTED))
            shot_btn.setIconSize(QSize(13, 13))
            shot_btn.clicked.connect(lambda: self._on_take_screenshot(dev))
            layout.addWidget(shot_btn)

        if dev.is_virtual:
            layout.addWidget(self._section_label("EMULATOR ACTIONS"))
            avd_n = dev.avd_name or dev.name

            if dev.is_online or dev.status.lower() in ("running", "booting"):
                restart_btn = QPushButton("Restart Emulator")
                restart_btn.setIcon(get_icon("rotate-cw", size=13, color=TEXT_MUTED))
                restart_btn.setIconSize(QSize(13, 13))
                restart_btn.clicked.connect(
                    lambda _=None, n=avd_n: self._dev_service.restart_emulator(n)
                )
                layout.addWidget(restart_btn)

                stop_btn = QPushButton("Stop Emulator")
                stop_btn.setIcon(get_icon("square", size=13, color="#ef4444"))
                stop_btn.setIconSize(QSize(13, 13))
                stop_btn.clicked.connect(lambda _=None, n=avd_n: self._dev_service.stop_emulator(n))
                layout.addWidget(stop_btn)
            else:
                start_btn = QPushButton("Start Emulator")
                start_btn.setIcon(get_icon("play", size=13, color="#10b981"))
                start_btn.setIconSize(QSize(13, 13))
                start_btn.clicked.connect(lambda _=None, n=avd_n: self._on_start_emulator(n))
                layout.addWidget(start_btn)

            side_del_btn = QPushButton("Delete Emulator")
            side_del_btn.setIcon(get_icon("trash-2", size=13, color="#ef4444"))
            side_del_btn.setIconSize(QSize(13, 13))
            side_del_btn.setProperty("role", "danger")
            side_del_btn.clicked.connect(lambda _=None, d=dev: self._on_delete_emulator(d))
            layout.addWidget(side_del_btn)

        return card

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #5c5f66; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; margin-top: 6px;"
        )
        return lbl

    def _property_row(self, label: str, value: str) -> QHBoxLayout:
        row = QHBoxLayout()
        key = QLabel(label)
        key.setStyleSheet("color: #9ca3af; font-size: 11px;")
        key.setFixedWidth(85)
        val = QLabel(value)
        val.setStyleSheet("color: #e5e7eb; font-size: 11px; font-family: monospace;")
        row.addWidget(key)
        row.addWidget(val, 1)
        return row

    def _swap_detail(self, new_detail: QWidget) -> None:
        new_detail.setFixedWidth(320)
        self._content_row.replaceWidget(self._detail_panel, new_detail)
        self._detail_panel.setParent(None)
        self._detail_panel.deleteLater()
        self._detail_panel = new_detail

    # -------------------------------------------------------------------------
    # Wi-Fi and Refresh Handlers
    # -------------------------------------------------------------------------
    def _on_connect_wifi_clicked(self) -> None:
        target = self._wifi_input.text().strip()
        if not target:
            QMessageBox.warning(
                self,
                "Missing Address",
                "Please enter an IP address or host:port to connect over Wi-Fi.",
            )
            return

        self._wifi_btn.setEnabled(False)
        self._wifi_btn.setText("Connecting...")
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.processEvents()

        try:
            success, msg = self._dev_service.connect_wireless(target)
            if success:
                QMessageBox.information(
                    self, "Wi-Fi Connected", f"Successfully connected to {target}!\n\n{msg}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Wi-Fi Connection Failed",
                    f"Could not connect to {target}.\n\n{msg}\n\n"
                    "Ensure device and PC are on the same Wi-Fi network.",
                )
        except Exception as exc:
            QMessageBox.warning(self, "Wi-Fi Error", str(exc))
        finally:
            self._wifi_btn.setEnabled(True)
            self._wifi_btn.setText("Connect Wi-Fi")

    def _on_refresh_clicked(self) -> None:
        self._dev_service.refresh()
        self._check_environment_status(force=True, async_check=True)

    def _on_take_screenshot(self, dev: ManagedDevice) -> None:
        if not dev.serial or not dev.is_online:
            QMessageBox.warning(
                self, "Device Not Ready", "Device is not currently online to capture a screenshot."
            )
            return
        try:
            shot_path = self._dev_service.take_screenshot(dev.serial)
            dialog = ScreenshotViewerDialog(shot_path, device_label=dev.name, parent=self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.warning(self, "Screenshot Failed", f"Could not capture screenshot: {exc}")

    def _clear_layout(self, layout: QLayout | None) -> None:
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    @override
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._dev_service.start_polling(page_visible=True)
        self._check_environment_status(force=False)

    @override
    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._dev_service.set_page_visible(False)
