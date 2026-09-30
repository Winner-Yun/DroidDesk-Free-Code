"""Screen Mirror Page: Live device screen sharing and remote interaction via scrcpy.
Uses the native, unconstrained scrcpy window for zero-latency, razor-sharp real device fidelity.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.core.models import Device, ScreenConfig
from droiddesk.ui.dialogs.screenshot_dialog import ScreenshotViewerDialog
from droiddesk.ui.dialogs.video_dialog import VideoRecordingDialog
from droiddesk.ui.theme import (
    ACCENT_GREEN,
    ACCENT_RED,
    BORDER_LIGHT,
    TEXT_MUTED,
    get_icon,
)
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.status_pill import TagPill


class ScreenMirrorPage(QWidget):
    """Screen mirror mission control orchestrating native scrcpy sessions and device control."""

    navigate_requested = Signal(str)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._screen_service = ctx.screen_service
        self._device_service = ctx.device_service

        self._devices: list[Device] = []
        self._selected_serial: str | None = None
        self._is_recording = False
        self._session_seconds = 0
        self._screen_w = 1080
        self._screen_h = 2400

        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # ---------------------------------------------------------------------
        # Header & Actions
        # ---------------------------------------------------------------------
        self._header = PageHeader(
            "Screen Mirror",
            "Live, low-latency device screen sharing and remote interaction via scrcpy.",
        )

        # Device selector
        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(210)
        self._device_combo.currentIndexChanged.connect(self._on_device_combo_changed)
        self._header.add_action(self._device_combo)

        # Bring to front button
        self._focus_btn = QPushButton("Bring Window to Front")
        self._focus_btn.setIcon(get_icon("external-link", size=13, color=TEXT_MUTED))
        self._focus_btn.setIconSize(QSize(13, 13))
        self._focus_btn.clicked.connect(self._on_focus_window)
        self._focus_btn.setEnabled(False)
        self._header.add_action(self._focus_btn)

        # Record screen button
        self._record_btn = QPushButton("Record Screen")
        self._record_btn.setCheckable(True)
        self._record_btn.setIcon(get_icon("video", size=13, color=TEXT_MUTED))
        self._record_btn.setIconSize(QSize(13, 13))
        self._record_btn.clicked.connect(self._on_record_toggled)
        self._header.add_action(self._record_btn)

        # Start / Stop primary action button
        self._toggle_btn = QPushButton("Start Mirroring")
        self._toggle_btn.setProperty("role", "primary")
        self._toggle_btn.setIcon(get_icon("play", size=13, color="#ffffff"))
        self._toggle_btn.setIconSize(QSize(13, 13))
        self._toggle_btn.clicked.connect(self._on_toggle_mirroring)
        self._header.add_action(self._toggle_btn)

        outer.addWidget(self._header)

        # ---------------------------------------------------------------------
        # Content Workspace (Live Session Center on Left, Controls on Right)
        # ---------------------------------------------------------------------
        self._workspace = QHBoxLayout()
        self._workspace.setSpacing(14)

        # Left / Center: Session Dashboard Card
        self._viewport_card = Card()
        self._viewport_layout = self._viewport_card.body_layout()
        self._viewport_layout.setContentsMargins(18, 18, 18, 18)

        # Stacked widget separating Inactive/Ready states from Active Session state
        self._view_stack = QStackedWidget()

        # Stack 0: Inactive / Empty / Ready to Mirror
        self._empty_holder = QWidget()
        self._empty_layout = QVBoxLayout(self._empty_holder)
        self._empty_layout.setContentsMargins(0, 0, 0, 0)
        self._view_stack.addWidget(self._empty_holder)

        # Stack 1: Active Session Dashboard
        self._active_holder = self._build_active_session_panel()
        self._view_stack.addWidget(self._active_holder)

        self._viewport_layout.addWidget(self._view_stack, 1)
        self._workspace.addWidget(self._viewport_card, 1)

        # Right: Quick Controls & Settings Sidebar
        self._side_panel = self._build_side_panel()
        self._side_panel.setFixedWidth(290)
        self._workspace.addWidget(self._side_panel)

        outer.addLayout(self._workspace, 1)

        # Timer for live session duration counter
        self._session_timer = QTimer(self)
        self._session_timer.setInterval(1000)
        self._session_timer.timeout.connect(self._on_session_tick)

        # Dedicated timer for screen recording duration counter
        self._record_timer = QTimer(self)
        self._record_timer.setInterval(1000)
        self._record_timer.timeout.connect(self._on_record_tick)
        self._record_seconds = 0

        # Connect service signals
        if self._screen_service:
            self._screen_service.session_started.connect(self._on_session_started)
            self._screen_service.session_stopped.connect(self._on_session_stopped)
            self._screen_service.session_error.connect(self._on_session_error)
            self._screen_service.resolution_ready.connect(self._on_resolution_ready)
            self._screen_service.recording_started.connect(self._on_recording_started)
            self._screen_service.recording_stopped.connect(self._on_recording_stopped)
            self._screen_service.recording_saved.connect(self._on_recording_saved)
            self._screen_service.recording_error.connect(self._on_recording_error)

        if self._device_service:
            self._device_service.devices_changed.connect(self._on_devices_changed)
            self._on_devices_changed(self._device_service.devices())

        self._update_viewport_state()

    # -------------------------------------------------------------------------
    # UI Building Helpers
    # -------------------------------------------------------------------------

    def _build_active_session_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Hero Icon & Header
        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("smartphone", size=48, color=ACCENT_GREEN).pixmap(48, 48))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        self._active_title_lbl = QLabel("Screen Mirroring Active")
        self._active_title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #ffffff;")
        self._active_title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._active_title_lbl)

        self._active_desc_lbl = QLabel(
            "The device display is streaming in its original, high-resolution scrcpy window.\n"
            "Enjoy true 60 FPS hardware performance with full mouse, touch, and keyboard support."
        )
        self._active_desc_lbl.setProperty("role", "muted")
        self._active_desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._active_desc_lbl.setWordWrap(True)
        layout.addWidget(self._active_desc_lbl)

        # Resolution & Status Tag Row
        tags_row = QHBoxLayout()
        tags_row.setSpacing(10)
        tags_row.addStretch(1)

        self._res_pill = TagPill("1080 x 2400")
        self._fps_pill = TagPill("60 FPS")
        self._live_pill = TagPill("Hardware Accelerated")
        self._live_pill.setStyleSheet(f"color: {ACCENT_GREEN}; border-color: {ACCENT_GREEN};")

        tags_row.addWidget(self._res_pill)
        tags_row.addWidget(self._fps_pill)
        tags_row.addWidget(self._live_pill)
        tags_row.addStretch(1)
        layout.addLayout(tags_row)

        # Primary Actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)

        focus_action_btn = QPushButton("Bring Window to Front")
        focus_action_btn.setProperty("role", "primary")
        focus_action_btn.setIcon(get_icon("external-link", size=14, color="#ffffff"))
        focus_action_btn.clicked.connect(self._on_focus_window)
        btn_row.addWidget(focus_action_btn)

        stop_action_btn = QPushButton("Stop Mirroring")
        stop_action_btn.setStyleSheet(
            f"background-color: {ACCENT_RED}; color: #ffffff; border: none;"
        )
        stop_action_btn.setIcon(get_icon("square", size=14, color="#ffffff"))
        stop_action_btn.clicked.connect(self._on_toggle_mirroring)
        btn_row.addWidget(stop_action_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Shortcuts Guide Card
        guide_box = QFrame()
        guide_box.setObjectName("guideBox")
        guide_box.setStyleSheet(
            f"#guideBox {{ background-color: rgba(255, 255, 255, 0.03); "
            f"border: 1px solid {BORDER_LIGHT}; border-radius: 10px; padding: 14px; }}"
        )
        guide_box.setMaximumWidth(520)
        g_layout = QVBoxLayout(guide_box)
        g_layout.setSpacing(8)

        g_header = QLabel("WINDOW SHORTCUTS & GESTURES")
        g_header.setProperty("role", "muted")
        g_header.setStyleSheet("font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        g_layout.addWidget(g_header)

        items = [
            ("Resize Window", "Drag window edges freely to scale without blur"),
            ("Alt + F", "Toggle Fullscreen mode"),
            ("Alt + G", "Scale to 1:1 pixel-perfect native resolution"),
            ("Alt + W", "Remove black letterbox borders"),
            ("Drag & Drop APK", "Drop an APK file onto the phone window to install"),
            ("Mouse & Keyboard", "Left click = tap, Right click = back, Middle click = home"),
        ]

        for shortcut, desc in items:
            row = QHBoxLayout()
            key_lbl = QLabel(f"<b>{shortcut}</b>")
            key_lbl.setStyleSheet("color: #60a5fa; font-size: 12px; min-width: 140px;")
            desc_lbl = QLabel(desc)
            desc_lbl.setProperty("role", "muted")
            desc_lbl.setStyleSheet("font-size: 12px;")
            row.addWidget(key_lbl)
            row.addWidget(desc_lbl, 1)
            g_layout.addLayout(row)

        layout.addWidget(guide_box, 0, Qt.AlignmentFlag.AlignCenter)
        return panel

    def _build_side_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 1. Android Virtual Navigation Controls
        nav_card = Card()
        nav_layout = nav_card.body_layout()
        nav_header = QLabel("DEVICE NAVIGATION")
        nav_header.setProperty("role", "muted")
        nav_layout.addWidget(nav_header)

        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(8)

        self._back_btn = QPushButton("Back")
        self._back_btn.setIcon(get_icon("arrow-left", size=13, color=TEXT_MUTED))
        self._back_btn.clicked.connect(self._on_nav_back)
        btn_row1.addWidget(self._back_btn)

        self._home_btn = QPushButton("Home")
        self._home_btn.setIcon(get_icon("circle", size=13, color=TEXT_MUTED))
        self._home_btn.clicked.connect(self._on_nav_home)
        btn_row1.addWidget(self._home_btn)

        self._recents_btn = QPushButton("Recents")
        self._recents_btn.setIcon(get_icon("square", size=13, color=TEXT_MUTED))
        self._recents_btn.clicked.connect(self._on_nav_recents)
        btn_row1.addWidget(self._recents_btn)

        nav_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(8)

        self._power_btn = QPushButton("Power / Lock")
        self._power_btn.setIcon(get_icon("power", size=13, color=TEXT_MUTED))
        self._power_btn.clicked.connect(self._on_nav_power)
        btn_row2.addWidget(self._power_btn)

        self._rotate_btn = QPushButton("Rotate")
        self._rotate_btn.setIcon(get_icon("rotate-cw", size=13, color=TEXT_MUTED))
        self._rotate_btn.clicked.connect(self._on_nav_rotate)
        btn_row2.addWidget(self._rotate_btn)

        nav_layout.addLayout(btn_row2)

        vol_row = QHBoxLayout()
        vol_row.setSpacing(8)

        self._vol_down_btn = QPushButton("Vol -")
        self._vol_down_btn.setIcon(get_icon("volume-1", size=13, color=TEXT_MUTED))
        self._vol_down_btn.clicked.connect(self._on_nav_vol_down)
        vol_row.addWidget(self._vol_down_btn)

        self._vol_up_btn = QPushButton("Vol +")
        self._vol_up_btn.setIcon(get_icon("volume-2", size=13, color=TEXT_MUTED))
        self._vol_up_btn.clicked.connect(self._on_nav_vol_up)
        vol_row.addWidget(self._vol_up_btn)

        self._quick_shot_btn = QPushButton("Capture")
        self._quick_shot_btn.setIcon(get_icon("camera", size=13, color=TEXT_MUTED))
        self._quick_shot_btn.clicked.connect(self._on_quick_screenshot)
        vol_row.addWidget(self._quick_shot_btn)

        nav_layout.addLayout(vol_row)
        layout.addWidget(nav_card)

        # 2. Quality & Presets Card
        settings_card = Card()
        settings_layout = settings_card.body_layout()

        set_header = QLabel("STREAM PRESETS")
        set_header.setProperty("role", "muted")
        settings_layout.addWidget(set_header)

        # Max size
        res_row = QHBoxLayout()
        res_label = QLabel("Max Size:")
        res_label.setProperty("role", "muted")
        self._res_combo = QComboBox()
        self._res_combo.addItem("1080p (Recommended)", 1080)
        self._res_combo.addItem("720p (Low Bandwidth)", 720)
        self._res_combo.addItem("1440p (High Res)", 1440)
        self._res_combo.addItem("Native (Original)", 0)
        res_row.addWidget(res_label)
        res_row.addWidget(self._res_combo, 1)
        settings_layout.addLayout(res_row)

        # Framerate
        fps_row = QHBoxLayout()
        fps_label = QLabel("Framerate:")
        fps_label.setProperty("role", "muted")
        self._fps_combo = QComboBox()
        self._fps_combo.addItem("60 FPS (Fluid)", 60)
        self._fps_combo.addItem("30 FPS (Battery Saver)", 30)
        fps_row.addWidget(fps_label)
        fps_row.addWidget(self._fps_combo, 1)
        settings_layout.addLayout(fps_row)

        # Bitrate
        bit_row = QHBoxLayout()
        bit_label = QLabel("Bitrate:")
        bit_label.setProperty("role", "muted")
        self._bit_combo = QComboBox()
        self._bit_combo.addItem("8 Mbps (Balanced)", 8)
        self._bit_combo.addItem("16 Mbps (Crisp)", 16)
        self._bit_combo.addItem("4 Mbps (Fast)", 4)
        bit_row.addWidget(bit_label)
        bit_row.addWidget(self._bit_combo, 1)
        settings_layout.addLayout(bit_row)

        # Checkboxes
        self._always_on_top_cb = QCheckBox("Keep mirror window on top")
        self._always_on_top_cb.setChecked(True)
        self._always_on_top_cb.setToolTip(
            "Floats the mirror window conveniently over other windows."
        )
        settings_layout.addWidget(self._always_on_top_cb)

        self._stay_awake_cb = QCheckBox("Keep device awake")
        self._stay_awake_cb.setChecked(True)
        settings_layout.addWidget(self._stay_awake_cb)

        self._turn_off_screen_cb = QCheckBox("Turn device screen off")
        self._turn_off_screen_cb.setToolTip("Turn off physical device display while streaming.")
        settings_layout.addWidget(self._turn_off_screen_cb)

        self._show_touches_cb = QCheckBox("Show touch indicators")
        self._show_touches_cb.setToolTip("Displays physical touch dots on the screen.")
        settings_layout.addWidget(self._show_touches_cb)

        self._forward_audio_cb = QCheckBox("Forward device audio")
        self._forward_audio_cb.setToolTip("Forward audio output (requires Android 11+).")
        settings_layout.addWidget(self._forward_audio_cb)

        # Wire preset signals so changes take effect
        self._res_combo.currentIndexChanged.connect(self._on_preset_changed)
        self._fps_combo.currentIndexChanged.connect(self._on_preset_changed)
        self._bit_combo.currentIndexChanged.connect(self._on_preset_changed)
        self._always_on_top_cb.toggled.connect(self._on_always_on_top_toggled)
        self._stay_awake_cb.toggled.connect(self._on_preset_changed)
        self._turn_off_screen_cb.toggled.connect(self._on_preset_changed)
        self._show_touches_cb.toggled.connect(self._on_preset_changed)
        self._forward_audio_cb.toggled.connect(self._on_preset_changed)

        self._apply_presets_btn = QPushButton("Apply Presets")
        self._apply_presets_btn.setIcon(get_icon("rotate-cw", size=13, color=TEXT_MUTED))
        self._apply_presets_btn.setIconSize(QSize(13, 13))
        self._apply_presets_btn.setToolTip("Apply stream presets to the live mirror session")
        self._apply_presets_btn.clicked.connect(self._on_apply_presets)
        settings_layout.addWidget(self._apply_presets_btn)

        layout.addWidget(settings_card)

        # 3. Session Info Card
        self._info_card = Card()
        self._info_layout = self._info_card.body_layout()

        info_header = QLabel("SESSION STATUS")
        info_header.setProperty("role", "muted")
        self._info_layout.addWidget(info_header)

        self._status_pill = TagPill("Disconnected")
        self._duration_lbl = QLabel("Duration: 00:00")
        self._duration_lbl.setProperty("role", "muted")

        status_row = QHBoxLayout()
        status_row.addWidget(self._status_pill)
        status_row.addStretch(1)
        status_row.addWidget(self._duration_lbl)
        self._info_layout.addLayout(status_row)

        # Screen recording status row
        rec_row = QHBoxLayout()
        self._rec_status_pill = TagPill("Standby")
        self._rec_duration_lbl = QLabel("")
        self._rec_duration_lbl.setProperty("role", "muted")
        rec_row.addWidget(self._rec_status_pill)
        rec_row.addStretch(1)
        rec_row.addWidget(self._rec_duration_lbl)
        self._info_layout.addLayout(rec_row)

        layout.addWidget(self._info_card)
        layout.addStretch(1)

        scroll.setWidget(content)
        return scroll

    # -------------------------------------------------------------------------
    # Viewport & State Management (via QStackedWidget)
    # -------------------------------------------------------------------------

    def _clear_empty_state(self) -> None:
        while self._empty_layout.count():
            item = self._empty_layout.takeAt(0)
            if item is not None and item.widget() is not None:
                w = item.widget()
                if w is not None:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()

    def _update_viewport_state(self) -> None:
        # Check if scrcpy is available
        if not self._screen_service or not self._screen_service.is_available():
            self._show_scrcpy_missing_state()
            self._toggle_btn.setEnabled(False)
            self._focus_btn.setEnabled(False)
            self._view_stack.setCurrentIndex(0)
            return

        # Check if devices connected
        if not self._selected_serial:
            self._show_no_devices_state()
            self._toggle_btn.setEnabled(False)
            self._focus_btn.setEnabled(False)
            self._view_stack.setCurrentIndex(0)
            return

        self._toggle_btn.setEnabled(True)

        # Check if mirroring is active
        if self._screen_service.is_mirroring(self._selected_serial):
            self._focus_btn.setEnabled(True)
            self._view_stack.setCurrentIndex(1)
        else:
            self._focus_btn.setEnabled(False)
            self._show_ready_to_mirror_state()
            self._view_stack.setCurrentIndex(0)

    def _show_scrcpy_missing_state(self) -> None:
        self._clear_empty_state()
        empty = EmptyStateWidget(
            title="scrcpy Not Detected",
            message=(
                "scrcpy is required for ultra-fast, zero-latency Android screen mirroring.\n\n"
                "Install scrcpy via winget or configure its path in Settings."
            ),
            button_text="Install via winget",
            show_button=True,
            parent=self._empty_holder,
        )
        empty.upload_requested.connect(self._on_install_scrcpy_winget)

        settings_btn = QPushButton("Open Settings")
        settings_btn.setIcon(get_icon("settings", size=13, color=TEXT_MUTED))
        settings_btn.clicked.connect(lambda: self.navigate_requested.emit("settings"))

        dl_btn = QPushButton("Download from GitHub")
        dl_btn.setIcon(get_icon("external-link", size=13, color=TEXT_MUTED))
        dl_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/Genymobile/scrcpy/releases/latest")
            )
        )

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(settings_btn)
        btn_row.addWidget(dl_btn)
        btn_row.addStretch(1)

        wrapper = QWidget(self._empty_holder)
        w_layout = QVBoxLayout(wrapper)
        w_layout.addWidget(empty)
        w_layout.addLayout(btn_row)
        w_layout.addStretch(1)

        self._empty_layout.addWidget(wrapper)

    def _show_no_devices_state(self) -> None:
        self._clear_empty_state()
        empty = EmptyStateWidget(
            title="No Device Selected",
            message=(
                "Connect an Android physical device or start an emulator to begin screen sharing.\n"
                "Ensure USB Debugging is authorized on the device."
            ),
            button_text="Refresh Devices",
            show_button=True,
            parent=self._empty_holder,
        )
        empty.upload_requested.connect(
            lambda: self._device_service.refresh() if self._device_service else None
        )
        self._empty_layout.addWidget(empty)

    def _show_ready_to_mirror_state(self) -> None:
        self._clear_empty_state()
        dev = self._get_selected_device()
        model_name = dev.model if dev and dev.model else (self._selected_serial or "Android Device")

        empty = EmptyStateWidget(
            title=f"Ready to Mirror {model_name}",
            message=(
                "Stream live screen at original crystal-clear resolution with zero blur or lag.\n"
                "The native mirror window can be freely resized or made full screen (Alt+F).\n"
                "Click Start Mirroring to launch the display."
            ),
            button_text="Start Screen Mirror",
            show_button=True,
            parent=self._empty_holder,
        )
        empty.upload_requested.connect(self._on_toggle_mirroring)
        self._empty_layout.addWidget(empty)

    # -------------------------------------------------------------------------
    # Actions & Slots
    # -------------------------------------------------------------------------

    def _on_focus_window(self) -> None:
        """Bring the active scrcpy window to the foreground."""
        if self._screen_service:
            self._screen_service.focus_window()

    def _get_current_screen_config(self) -> ScreenConfig:
        max_sz = self._res_combo.currentData()
        fps = self._fps_combo.currentData()
        bit = self._bit_combo.currentData()
        return ScreenConfig(
            max_size=int(max_sz) if max_sz is not None else 1080,
            max_fps=int(fps) if fps is not None else 60,
            bit_rate=int(bit) if bit is not None else 8,
            stay_awake=self._stay_awake_cb.isChecked(),
            turn_screen_off=self._turn_off_screen_cb.isChecked(),
            show_touches=self._show_touches_cb.isChecked(),
            forward_audio=self._forward_audio_cb.isChecked(),
            always_on_top=self._always_on_top_cb.isChecked(),
            embedded=False,  # Native, unforced window per user preference
        )

    def _on_preset_changed(self) -> None:
        if (
            self._screen_service
            and self._selected_serial
            and self._screen_service.is_mirroring(self._selected_serial)
        ):
            self._apply_presets_btn.setText("Restart with New Presets")
            self._apply_presets_btn.setStyleSheet(
                "background-color: #2563eb; color: #ffffff; border: none; font-weight: 600;"
            )

    def _on_always_on_top_toggled(self, checked: bool) -> None:
        if self._screen_service:
            self._screen_service.set_always_on_top(checked)

    def _on_apply_presets(self) -> None:
        if (
            self._screen_service
            and self._selected_serial
            and self._screen_service.is_mirroring(self._selected_serial)
        ):
            self._restart_session()
        self._apply_presets_btn.setText("Presets Applied")
        self._apply_presets_btn.setStyleSheet("")
        QTimer.singleShot(2000, lambda: self._apply_presets_btn.setText("Apply Presets"))

    def _on_record_toggled(self) -> None:
        if not self._screen_service or not self._selected_serial:
            self._record_btn.setChecked(False)
            return

        if self._screen_service.is_recording(self._selected_serial):
            self._record_btn.setEnabled(False)
            self._record_btn.setText("Saving Video...")
            self._screen_service.stop_recording(self._selected_serial)
        else:
            cfg = self._get_current_screen_config()
            started = self._screen_service.start_recording(self._selected_serial, config=cfg)
            if not started:
                self._record_btn.setChecked(False)

    def _on_recording_started(self, serial: str, path: Path) -> None:
        if serial != self._selected_serial:
            return
        self._record_seconds = 0
        self._record_timer.start()
        self._record_btn.setChecked(True)
        self._record_btn.setEnabled(True)
        self._record_btn.setText("● Stop Recording (00:00)")
        self._record_btn.setStyleSheet(
            f"background-color: {ACCENT_RED}; color: #ffffff; font-weight: 700; border: none;"
        )
        self._rec_status_pill.setText("Recording")
        self._rec_status_pill.setStyleSheet(f"color: {ACCENT_RED}; border-color: {ACCENT_RED};")
        self._rec_duration_lbl.setText("Recording: 00:00")

    def _on_recording_stopped(self, serial: str, path: Path) -> None:
        if serial != self._selected_serial:
            return
        self._record_timer.stop()
        self._record_btn.setChecked(False)
        self._record_btn.setEnabled(True)
        self._record_btn.setText("Record Screen")
        self._record_btn.setStyleSheet("")
        self._rec_status_pill.setText("Standby")
        self._rec_status_pill.setStyleSheet("")
        self._rec_duration_lbl.setText("")

    def _on_record_tick(self) -> None:
        self._record_seconds += 1
        mins = self._record_seconds // 60
        secs = self._record_seconds % 60
        time_str = f"{mins:02d}:{secs:02d}"
        self._record_btn.setText(f"● Stop Recording ({time_str})")
        self._rec_duration_lbl.setText(f"Recording: {time_str}")

    def _on_recording_saved(self, serial: str, video_path: Path) -> None:
        dev = self._get_selected_device()
        label = f"{dev.model or 'Android'} ({serial})" if dev else serial
        dialog = VideoRecordingDialog(video_path, device_label=label, parent=self)
        dialog.exec()

    def _on_recording_error(self, serial: str, error_message: str) -> None:
        self._on_recording_stopped(serial, Path())
        QMessageBox.warning(self, "Screen Recording Failed", error_message)

    def _on_toggle_mirroring(self) -> None:
        if not self._screen_service or not self._selected_serial:
            return

        if self._screen_service.is_mirroring(self._selected_serial):
            self._screen_service.stop_mirroring(self._selected_serial)
        else:
            self._start_session()

    def _restart_session(self) -> None:
        """Smoothly restart mirroring using updated presets."""
        if not self._screen_service or not self._selected_serial:
            return
        if self._screen_service.is_mirroring(self._selected_serial):
            self._screen_service.stop_mirroring(self._selected_serial)
            QTimer.singleShot(350, self._start_session)
        else:
            self._start_session()

    def _start_session(self) -> None:
        if not self._screen_service or not self._selected_serial:
            return

        cfg = self._get_current_screen_config()
        success = self._screen_service.start_mirroring(self._selected_serial, cfg)
        if not success:
            self._update_viewport_state()
        self._apply_presets_btn.setText("Apply Presets")
        self._apply_presets_btn.setStyleSheet("")

    def _on_session_started(self, serial: str) -> None:
        if serial != self._selected_serial:
            return

        self._toggle_btn.setText("Stop Mirroring")
        self._toggle_btn.setIcon(get_icon("square", size=13, color="#ffffff"))
        self._toggle_btn.setStyleSheet(f"background-color: {ACCENT_RED}; border: none;")

        self._status_pill.setText("Streaming (Live)")
        self._status_pill.setStyleSheet(f"color: {ACCENT_GREEN}; border-color: {ACCENT_GREEN};")

        dev = self._get_selected_device()
        model_name = dev.model if dev and dev.model else serial
        self._active_title_lbl.setText(f"Mirroring {model_name}")

        self._session_seconds = 0
        self._session_timer.start()

        # Query initial resolution from device
        if self._screen_service:
            w, h = self._screen_service.get_resolution(serial)
            self._screen_w = max(w, 100)
            self._screen_h = max(h, 100)
            self._res_pill.setText(f"{self._screen_w} x {self._screen_h}")

        self._fps_pill.setText(f"{self._fps_combo.currentData()} FPS")
        self._apply_presets_btn.setText("Apply Presets")
        self._apply_presets_btn.setStyleSheet("")
        self._update_viewport_state()

    def _on_session_stopped(self, serial: str) -> None:
        self._session_timer.stop()

        self._toggle_btn.setText("Start Mirroring")
        self._toggle_btn.setIcon(get_icon("play", size=13, color="#ffffff"))
        self._toggle_btn.setStyleSheet("")

        self._status_pill.setText("Disconnected")
        self._status_pill.setStyleSheet("")
        self._duration_lbl.setText("Duration: 00:00")
        self._apply_presets_btn.setText("Apply Presets")
        self._apply_presets_btn.setStyleSheet("")

        self._update_viewport_state()

    def _on_session_error(self, serial: str, error_message: str) -> None:
        QMessageBox.warning(self, "Screen Mirror Error", error_message)
        self._on_session_stopped(serial)

    def _on_resolution_ready(self, serial: str, width: int, height: int) -> None:
        if serial == self._selected_serial and width > 0 and height > 0:
            self._screen_w = width
            self._screen_h = height
            self._res_pill.setText(f"{width} x {height}")

    def _on_session_tick(self) -> None:
        self._session_seconds += 1
        mins = self._session_seconds // 60
        secs = self._session_seconds % 60
        self._duration_lbl.setText(f"Duration: {mins:02d}:{secs:02d}")

    def _on_devices_changed(self, devices: list[Device]) -> None:
        self._devices = [d for d in devices if d.state == "device"]
        prev_serial = self._selected_serial

        # If currently actively mirroring, keep session intact and do not wipe canvas
        is_mirroring = (
            self._screen_service is not None
            and self._selected_serial is not None
            and self._screen_service.is_mirroring(self._selected_serial)
        )

        self._device_combo.blockSignals(True)
        self._device_combo.clear()

        for d in self._devices:
            label = f"{d.model or 'Android'} ({d.serial})"
            self._device_combo.addItem(label, d.serial)

        if not self._devices:
            self._selected_serial = None
        elif prev_serial and any(d.serial == prev_serial for d in self._devices):
            self.select_device(prev_serial)
        else:
            self.select_device(self._devices[0].serial)

        self._device_combo.blockSignals(False)

        if not is_mirroring:
            self._update_viewport_state()

    def _on_device_combo_changed(self, index: int) -> None:
        if index >= 0:
            serial = self._device_combo.itemData(index)
            if serial and serial != self._selected_serial:
                # If currently mirroring old device, stop
                if self._screen_service and self._screen_service.is_mirroring():
                    self._screen_service.stop_mirroring()
                self._selected_serial = serial
                self._update_viewport_state()

    def select_device(self, serial: str) -> None:
        """Programmatically select a device serial in the combo box."""
        for i in range(self._device_combo.count()):
            if self._device_combo.itemData(i) == serial:
                self._device_combo.setCurrentIndex(i)
                self._selected_serial = serial
                return
        self._selected_serial = serial

    def _get_selected_device(self) -> Device | None:
        if not self._selected_serial:
            return None
        return next((d for d in self._devices if d.serial == self._selected_serial), None)

    # -------------------------------------------------------------------------
    # Quick Control Navigation Actions
    # -------------------------------------------------------------------------

    def _on_nav_back(self) -> None:
        if self._screen_service and self._selected_serial:
            self._screen_service.send_back(self._selected_serial)

    def _on_nav_home(self) -> None:
        if self._screen_service and self._selected_serial:
            self._screen_service.send_home(self._selected_serial)

    def _on_nav_recents(self) -> None:
        if self._screen_service and self._selected_serial:
            self._screen_service.send_app_switch(self._selected_serial)

    def _on_nav_power(self) -> None:
        if self._screen_service and self._selected_serial:
            self._screen_service.send_power(self._selected_serial)

    def _on_nav_vol_up(self) -> None:
        if self._screen_service and self._selected_serial:
            self._screen_service.send_volume_up(self._selected_serial)

    def _on_nav_vol_down(self) -> None:
        if self._screen_service and self._selected_serial:
            self._screen_service.send_volume_down(self._selected_serial)

    def _on_nav_rotate(self) -> None:
        if self._screen_service and self._selected_serial:
            self._screen_service.send_rotate(self._selected_serial)

    def _on_quick_screenshot(self) -> None:
        if not self._device_service or not self._selected_serial:
            return
        try:
            shot_path = self._device_service.take_screenshot(self._selected_serial)
            dev = self._get_selected_device()
            label = (
                f"{dev.model or 'Android'} ({self._selected_serial})"
                if dev
                else self._selected_serial
            )
            dialog = ScreenshotViewerDialog(shot_path, device_label=label, parent=self)
            dialog.exec()
        except Exception as exc:
            QMessageBox.warning(self, "Screenshot Failed", str(exc))

    def _on_install_scrcpy_winget(self) -> None:
        """Trigger automated winget installation for scrcpy."""
        reply = QMessageBox.question(
            self,
            "Install scrcpy",
            "DroidDesk will run:\n\nwinget install Genymobile.scrcpy\n\nProceed with installation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                cmd = [
                    "cmd.exe", "/c", "start", "cmd.exe", "/k", "winget install Genymobile.scrcpy"
                ]
                subprocess.Popen(cmd)
            except Exception as exc:
                QMessageBox.warning(self, "Launch Error", f"Could not launch installer: {exc}")
