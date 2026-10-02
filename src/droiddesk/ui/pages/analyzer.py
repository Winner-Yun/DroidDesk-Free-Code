"""APK Analyzer page inspecting signature, permissions, and components."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.core.models import ApkInfo
from droiddesk.ui.theme import TEXT_MUTED, get_icon, is_light
from droiddesk.ui.widgets.card import PageHeader, StatCard
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.status_pill import TagPill

_API_LEVEL_NAMES: dict[int, str] = {
    21: "Android 5.0 (Lollipop)",
    22: "Android 5.1 (Lollipop)",
    23: "Android 6.0 (Marshmallow)",
    24: "Android 7.0 (Nougat)",
    25: "Android 7.1 (Nougat)",
    26: "Android 8.0 (Oreo)",
    27: "Android 8.1 (Oreo)",
    28: "Android 9.0 (Pie)",
    29: "Android 10",
    30: "Android 11",
    31: "Android 12",
    32: "Android 12L",
    33: "Android 13",
    34: "Android 14",
    35: "Android 15",
    36: "Android 16",
}

_PERMISSION_DESCRIPTIONS: dict[str, tuple[str, str, bool]] = {
    "android.permission.ACCESS_FINE_LOCATION": (
        "Precise Location",
        "Access precise GPS and network location",
        True,
    ),
    "android.permission.ACCESS_COARSE_LOCATION": (
        "Approximate Location",
        "Access approximate cell and Wi-Fi location",
        True,
    ),
    "android.permission.ACCESS_BACKGROUND_LOCATION": (
        "Background Location",
        "Access device location in the background without user interaction",
        True,
    ),
    "android.permission.CAMERA": (
        "Camera",
        "Capture photos and videos via device cameras",
        True,
    ),
    "android.permission.RECORD_AUDIO": (
        "Microphone",
        "Record audio and voice via the microphone",
        True,
    ),
    "android.permission.READ_CONTACTS": (
        "Read Contacts",
        "Access stored contacts and address books",
        True,
    ),
    "android.permission.WRITE_CONTACTS": (
        "Modify Contacts",
        "Add, edit, or delete stored contacts",
        True,
    ),
    "android.permission.GET_ACCOUNTS": (
        "Device Accounts",
        "Access the list of user accounts configured on device",
        True,
    ),
    "android.permission.READ_PHONE_STATE": (
        "Phone State",
        "Read phone status, cellular network info, and ongoing calls",
        True,
    ),
    "android.permission.READ_PHONE_NUMBERS": (
        "Phone Numbers",
        "Access device telephone numbers",
        True,
    ),
    "android.permission.CALL_PHONE": (
        "Initiate Calls",
        "Place phone calls directly without dialer confirmation",
        True,
    ),
    "android.permission.READ_CALL_LOG": (
        "Read Call Log",
        "Access incoming and outgoing phone call logs",
        True,
    ),
    "android.permission.WRITE_CALL_LOG": (
        "Modify Call Log",
        "Edit or delete entries in phone call history",
        True,
    ),
    "android.permission.SEND_SMS": (
        "Send SMS",
        "Send text messages which may incur carrier charges",
        True,
    ),
    "android.permission.RECEIVE_SMS": (
        "Receive SMS",
        "Intercept and process incoming SMS messages",
        True,
    ),
    "android.permission.READ_SMS": (
        "Read SMS",
        "Access private SMS and MMS messages stored on device",
        True,
    ),
    "android.permission.RECEIVE_MMS": (
        "Receive MMS",
        "Monitor and receive multimedia messages",
        True,
    ),
    "android.permission.READ_EXTERNAL_STORAGE": (
        "Read Shared Storage",
        "Read files from shared external storage / SD card",
        True,
    ),
    "android.permission.WRITE_EXTERNAL_STORAGE": (
        "Write Shared Storage",
        "Modify or delete files on shared external storage",
        True,
    ),
    "android.permission.MANAGE_EXTERNAL_STORAGE": (
        "All Files Access",
        "Broad, unrestricted access to all shared storage files",
        True,
    ),
    "android.permission.READ_MEDIA_IMAGES": (
        "Read Photo Media",
        "Access photos and image media from shared storage",
        True,
    ),
    "android.permission.READ_MEDIA_VIDEO": (
        "Read Video Media",
        "Access video recordings from shared storage",
        True,
    ),
    "android.permission.READ_MEDIA_AUDIO": (
        "Read Audio Media",
        "Access music and audio recordings from shared storage",
        True,
    ),
    "android.permission.SYSTEM_ALERT_WINDOW": (
        "Display Overlay",
        "Draw floating overlay windows on top of other running apps",
        True,
    ),
    "android.permission.WRITE_SETTINGS": (
        "Modify System Settings",
        "Change sensitive device system preferences and settings",
        True,
    ),
    "android.permission.REQUEST_INSTALL_PACKAGES": (
        "Install Packages",
        "Prompt user to install external APK package files",
        True,
    ),
    "android.permission.BIND_ACCESSIBILITY_SERVICE": (
        "Accessibility Service",
        "Monitor user interactions, screen content, and gestures",
        True,
    ),
    "android.permission.PACKAGE_USAGE_STATS": (
        "Usage Statistics",
        "Access component usage statistics and app activity history",
        True,
    ),
    "android.permission.POST_NOTIFICATIONS": (
        "Post Notifications",
        "Display notification banners and status bar alerts",
        False,
    ),
    "android.permission.INTERNET": (
        "Full Network Access",
        "Open network sockets and connect to the Internet",
        False,
    ),
    "android.permission.ACCESS_NETWORK_STATE": (
        "Network State",
        "View information about Wi-Fi and mobile network connections",
        False,
    ),
    "android.permission.ACCESS_WIFI_STATE": (
        "Wi-Fi State",
        "View Wi-Fi networking status and connected network details",
        False,
    ),
    "android.permission.VIBRATE": (
        "Control Vibration",
        "Trigger haptic feedback and device vibration motors",
        False,
    ),
    "android.permission.WAKE_LOCK": (
        "Prevent Sleep",
        "Prevent CPU from sleeping or screen from dimming",
        False,
    ),
    "android.permission.FOREGROUND_SERVICE": (
        "Foreground Service",
        "Run foreground service tasks visible in the notification drawer",
        False,
    ),
    "android.permission.RECEIVE_BOOT_COMPLETED": (
        "Run at Startup",
        "Automatically start services when the device finishes booting",
        False,
    ),
}


def _clear_layout(layout: QVBoxLayout | QHBoxLayout | QGridLayout | None) -> None:
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())  # type: ignore[arg-type]


class AnalyzerPage(QWidget):
    upload_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._apk_info: ApkInfo | None = None
        self._full_analysis_loaded = False

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("page")
        self.setProperty("role", "page")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "APK analyzer", "Everything derivable from the file without installing it."
        )
        outer.addWidget(header)

        self._identity_container = QWidget()
        self._identity_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._identity_layout = QVBoxLayout(self._identity_container)
        self._identity_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._identity_container)

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Permanent tab containers (transparent background, no wipe)
        self._sig_panel = QWidget()
        self._sig_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._sig_layout = QVBoxLayout(self._sig_panel)
        self._sig_layout.setContentsMargins(0, 0, 0, 0)

        self._perm_panel = QWidget()
        self._perm_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._perm_layout = QVBoxLayout(self._perm_panel)
        self._perm_layout.setContentsMargins(0, 0, 0, 0)

        self._comp_panel = QWidget()
        self._comp_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._comp_layout = QVBoxLayout(self._comp_panel)
        self._comp_layout.setContentsMargins(0, 0, 0, 0)

        self._setup_tabs()
        outer.addWidget(self._tabs, 1)

        self._empty_state = EmptyStateWidget(
            title="No APK Selected for Analysis",
            message=(
                "Select an APK from the app bar or upload an Android package "
                "(.apk / .aab) to inspect its signatures, permissions, and components."
            ),
            button_text="Upload APK",
        )
        self._empty_state.upload_requested.connect(self.upload_requested.emit)
        outer.addWidget(self._empty_state, 1)

        self._refresh_ui()

    def _setup_tabs(self) -> None:
        icon_color = "#4b5563" if is_light() else TEXT_MUTED
        self._tabs.clear()
        self._tabs.addTab(
            self._sig_panel, get_icon("award", size=14, color=icon_color), "Signature"
        )
        self._tabs.addTab(
            self._perm_panel, get_icon("key-round", size=14, color=icon_color), "Permissions"
        )
        self._tabs.addTab(
            self._comp_panel, get_icon("layers", size=14, color=icon_color), "Components"
        )

    def set_theme(self, mode: str) -> None:
        """Called when the application switches theme mode."""
        self._setup_tabs()
        self._refresh_ui()

    def load_apk(self, path: Path | None) -> None:
        if path is None or not path.is_file():
            self._apk_info = None
            self._full_analysis_loaded = False
            self._refresh_ui()
            return

        try:
            # Fast pyaxmlparser inspection (under 50ms): package, SDKs, permissions, components
            self._apk_info = self._ctx.apk_service.inspect(path)
            self._full_analysis_loaded = False
            self._refresh_ui()

            # If user is on the Signature tab, load signature details quickly
            if self._tabs.currentIndex() == 0:
                self._load_signature()
        except Exception as e:
            print(f"Fast inspection error: {e}")

    def _load_signature(self) -> None:
        if not self._apk_info or self._full_analysis_loaded:
            return
        try:
            # Fast apksigner verification (without heavy bytecode/resource parsing)
            self._apk_info = self._ctx.apk_service.inspect_full(self._apk_info.file_path)
            self._full_analysis_loaded = True
            self._refresh_signature_panel()
        except Exception as e:
            print(f"Signature inspection notice: {e}")

    def _on_open_apk(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open APK", "", "APK Files (*.apk)")
        if path:
            self.load_apk(Path(path))

    def _on_tab_changed(self, index: int) -> None:
        if index == 0 and not self._full_analysis_loaded:
            self._load_signature()

    def _refresh_ui(self) -> None:
        _clear_layout(self._identity_layout)

        if self._apk_info:
            self._empty_state.hide()
            self._identity_container.show()
            self._tabs.show()
            self._build_identity_bar()
            self._refresh_signature_panel()
            self._refresh_permissions_panel()
            self._refresh_components_panel()
        else:
            self._identity_container.hide()
            self._tabs.hide()
            self._empty_state.show()

    def _build_identity_bar(self) -> None:
        if not self._apk_info:
            return

        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(10)

        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name = QLabel(self._apk_info.file_path.name)
        name.setStyleSheet("font-size: 15px; font-weight: 700;")
        package = QLabel(self._apk_info.package_name)
        package.setProperty("role", "mono")
        name_col.addWidget(name)
        name_col.addWidget(package)
        layout.addLayout(name_col)
        layout.addStretch(1)

        size_mb = self._apk_info.size_bytes / (1024 * 1024)
        version_str = (
            f"{self._apk_info.version_name or '1.0'} ({self._apk_info.version_code or 1})"
        )
        layout.addWidget(TagPill(version_str))

        if self._apk_info.min_sdk:
            min_name = _API_LEVEL_NAMES.get(self._apk_info.min_sdk, "")
            min_label = f"min {self._apk_info.min_sdk}" + (
                f" ({min_name.split(' (')[0]})" if min_name else ""
            )
            layout.addWidget(TagPill(min_label))

        if self._apk_info.target_sdk:
            tgt_name = _API_LEVEL_NAMES.get(self._apk_info.target_sdk, "")
            tgt_label = f"target {self._apk_info.target_sdk}" + (
                f" ({tgt_name.split(' (')[0]})" if tgt_name else ""
            )
            layout.addWidget(TagPill(tgt_label))

        layout.addWidget(TagPill(f"{size_mb:.1f} MB"))

        if self._apk_info.debuggable is not None:
            dbg_text = "Debug build" if self._apk_info.debuggable else "Release build"
            layout.addWidget(TagPill(dbg_text))

        self._identity_layout.addWidget(bar)

    def _refresh_signature_panel(self) -> None:
        _clear_layout(self._sig_layout)
        if not self._apk_info:
            return

        panel = QWidget()
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(14)

        # 1. Signature schemes row
        layout.addWidget(self._label("SIGNATURE SCHEMES PRESENT", muted=True))
        schemes_row = QHBoxLayout()
        schemes_row.setSpacing(8)

        light = is_light()
        for n, label_name in [
            (1, "v1 (JAR)"),
            (2, "v2 (APK v2)"),
            (3, "v3 (Key Rotation)"),
            (31, "v3.1"),
            (4, "v4 (Streaming)"),
        ]:
            present = n in self._apk_info.signature_schemes
            pill = QLabel(label_name)
            if present:
                color = "#16a34a" if light else "#22c55e"
                bg = "rgba(22, 163, 74, 0.1)" if light else "rgba(34, 197, 94, 0.12)"
            else:
                color = "#9ca3af" if light else "#5c5f66"
                bg = "transparent"

            border_c = color if present else ("#d1d5db" if light else "#35373e")
            pill.setStyleSheet(
                f"border: 1px solid {border_c}; color: {color}; background: {bg}; "
                f"border-radius: 4px; padding: 3px 10px; font-weight: 700; font-size: 11px;"
            )
            schemes_row.addWidget(pill)

        # Verification pill
        is_verified = self._apk_info.signature_verified
        status_pill = QLabel(
            "Verified Signature" if is_verified else "Unverified / Debug Key"
        )
        status_color = (
            ("#16a34a" if light else "#22c55e")
            if is_verified
            else ("#d97706" if light else "#f59e0b")
        )
        status_bg = (
            ("rgba(22, 163, 74, 0.1)" if light else "rgba(34, 197, 94, 0.12)")
            if is_verified
            else ("rgba(217, 119, 6, 0.1)" if light else "rgba(245, 158, 11, 0.12)")
        )
        status_pill.setStyleSheet(
            f"border: 1px solid {status_color}; color: {status_color}; background: {status_bg}; "
            f"border-radius: 4px; padding: 3px 12px; font-weight: 700; font-size: 11px; margin-left: 12px;"
        )
        schemes_row.addWidget(status_pill)
        schemes_row.addStretch(1)
        layout.addLayout(schemes_row)

        # 2. Debug keystore warning banner
        cert_dn = self._apk_info.certificate_dn or ""
        is_debug = "android debug" in cert_dn.lower()
        if is_debug:
            banner = QFrame()
            banner.setObjectName("keystoreBanner")
            b_layout = QVBoxLayout(banner)
            b_layout.setContentsMargins(12, 10, 12, 10)
            b_layout.setSpacing(4)
            b_title = QLabel("Android Debug Keystore Signature")
            b_title.setObjectName("keystoreTitle")
            b_desc = QLabel(
                "This APK was signed with the default SDK debug key (debug.keystore). "
                "All debug APKs built on this machine share this exact same signature. "
                "Do not publish APKs signed with this key to production."
            )
            b_desc.setWordWrap(True)
            b_desc.setProperty("role", "muted")
            b_layout.addWidget(b_title)
            b_layout.addWidget(b_desc)
            layout.addWidget(banner)

        layout.addWidget(self._divider())

        # 3. Certificate details
        layout.addWidget(self._label("CERTIFICATE DETAILS", muted=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        row_idx = 0
        if cert_dn:
            key_label = QLabel("Subject / DN")
            key_label.setProperty("role", "muted")
            key_label.setFixedWidth(110)
            value_label = QLabel(cert_dn)
            value_label.setProperty("role", "mono")
            value_label.setWordWrap(True)
            grid.addWidget(key_label, row_idx, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value_label, row_idx, 1)

            cp_dn_btn = QPushButton("Copy")
            cp_dn_btn.setIcon(get_icon("copy", size=12, color=TEXT_MUTED))
            cp_dn_btn.setFixedHeight(26)
            cp_dn_btn.clicked.connect(
                lambda _, text=cert_dn, b=cp_dn_btn: self._copy_text(b, text)
            )
            grid.addWidget(cp_dn_btn, row_idx, 2, Qt.AlignmentFlag.AlignTop)
            row_idx += 1

        fingerprints = [
            ("SHA-256", self._apk_info.certificate_fingerprint_sha256),
            ("SHA-1", self._apk_info.certificate_fingerprint_sha1),
            ("MD5", self._apk_info.certificate_fingerprint_md5),
        ]
        for name, fp in fingerprints:
            if fp:
                key_label = QLabel(name)
                key_label.setProperty("role", "muted")
                key_label.setFixedWidth(110)
                value_label = QLabel(fp)
                value_label.setProperty("role", "mono")
                value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(key_label, row_idx, 0)
                grid.addWidget(value_label, row_idx, 1)

                cp_btn = QPushButton("Copy")
                cp_btn.setIcon(get_icon("copy", size=12, color=TEXT_MUTED))
                cp_btn.setFixedHeight(26)
                cp_btn.clicked.connect(lambda _, text=fp, b=cp_btn: self._copy_text(b, text))
                grid.addWidget(cp_btn, row_idx, 2)
                row_idx += 1

        if row_idx == 0:
            no_cert_lbl = QLabel("No certificate details found (unsigned APK).")
            no_cert_lbl.setProperty("role", "muted")
            grid.addWidget(no_cert_lbl, 0, 0, 1, 2)

        layout.addLayout(grid)

        # 4. Source tool notice
        source_tool = self._apk_info.signature_source or "apksigner"
        source_note = (
            "Read by: apksigner verify --print-certs -v"
            if source_tool == "apksigner"
            else "Read by: APK signature inspector"
        )
        note = QLabel(source_note)
        note.setProperty("role", "muted")
        note.setStyleSheet("font-size: 11px;")
        layout.addWidget(note)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._sig_layout.addWidget(scroll)

    def _is_high_risk_permission(self, perm: str) -> bool:
        if perm in _PERMISSION_DESCRIPTIONS:
            return _PERMISSION_DESCRIPTIONS[perm][2]
        return any(
            risk in perm
            for risk in (
                "LOCATION",
                "CAMERA",
                "RECORD_AUDIO",
                "CONTACTS",
                "PHONE",
                "CALL",
                "SMS",
                "MMS",
                "STORAGE",
                "SYSTEM_ALERT",
                "SETTINGS",
                "INSTALL_PACKAGES",
                "ACCESSIBILITY",
                "USAGE_STATS",
            )
        )

    def _refresh_permissions_panel(self) -> None:
        _clear_layout(self._perm_layout)
        if not self._apk_info:
            return

        panel = QWidget()
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(12)

        perms = self._apk_info.permissions
        high_risk = [p for p in perms if self._is_high_risk_permission(p)]
        normal_perms = [p for p in perms if not self._is_high_risk_permission(p)]

        # Stat cards row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        stats_row.addWidget(StatCard(str(len(perms)), "Total Permissions"))
        stats_row.addWidget(StatCard(str(len(high_risk)), "High-Risk / Sensitive"))
        stats_row.addWidget(StatCard(str(len(normal_perms)), "Normal Permissions"))
        layout.addLayout(stats_row)

        # Search and Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        search_input = QLineEdit()
        search_input.setPlaceholderText("Filter permissions by name or keyword...")
        search_input.setClearButtonEnabled(True)
        search_input.setFixedHeight(32)
        filter_row.addWidget(search_input, 1)

        btn_all = QPushButton(f"All ({len(perms)})")
        btn_high = QPushButton(f"High-Risk ({len(high_risk)})")
        btn_norm = QPushButton(f"Normal ({len(normal_perms)})")

        for b in (btn_all, btn_high, btn_norm):
            b.setCheckable(True)
            b.setFixedHeight(32)
        btn_all.setChecked(True)

        filter_row.addWidget(btn_all)
        filter_row.addWidget(btn_high)
        filter_row.addWidget(btn_norm)
        layout.addLayout(filter_row)

        # List widget
        list_widget = QListWidget()
        list_widget.setSpacing(2)
        list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(list_widget, 1)

        active_filter = {"mode": "all", "query": ""}
        light = is_light()

        def update_perm_list() -> None:
            list_widget.clear()
            query = active_filter["query"].lower().strip()
            mode = active_filter["mode"]

            for p in perms:
                is_danger = self._is_high_risk_permission(p)
                if mode == "high" and not is_danger:
                    continue
                if mode == "norm" and is_danger:
                    continue

                info = _PERMISSION_DESCRIPTIONS.get(p)
                short_title = info[0] if info else p.rsplit(".", 1)[-1]
                desc = info[1] if info else ""

                if query:
                    searchable = f"{p} {short_title} {desc}".lower()
                    if query not in searchable:
                        continue

                item_w = QWidget()
                item_w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                iw_layout = QHBoxLayout(item_w)
                iw_layout.setContentsMargins(10, 8, 10, 8)
                iw_layout.setSpacing(10)

                pill = QLabel("HIGH RISK" if is_danger else "NORMAL")
                pill_color = (
                    ("#dc2626" if light else "#ef4444")
                    if is_danger
                    else ("#4b5563" if light else "#9ca3af")
                )
                pill_bg = (
                    ("rgba(220, 38, 38, 0.08)" if light else "rgba(239, 68, 68, 0.12)")
                    if is_danger
                    else ("#f3f4f6" if light else "rgba(255, 255, 255, 0.05)")
                )
                pill_border = (
                    ("#fca5a5" if light else "rgba(239, 68, 68, 0.35)")
                    if is_danger
                    else ("#d1d5db" if light else "#35373e")
                )
                pill.setStyleSheet(
                    f"border: 1px solid {pill_border}; color: {pill_color}; background: {pill_bg}; "
                    f"border-radius: 4px; padding: 2px 8px; font-weight: 700; font-size: 10px;"
                )
                pill.setFixedWidth(84)
                iw_layout.addWidget(pill)

                text_col = QVBoxLayout()
                text_col.setSpacing(2)
                t_lbl = QLabel(f"{short_title} — <span style='font-family: monospace;'>{p}</span>")
                t_lbl.setTextFormat(Qt.TextFormat.RichText)
                text_col.addWidget(t_lbl)
                if desc:
                    d_lbl = QLabel(desc)
                    d_lbl.setProperty("role", "muted")
                    d_lbl.setStyleSheet("font-size: 11px;")
                    text_col.addWidget(d_lbl)
                iw_layout.addLayout(text_col, 1)

                cp_btn = QPushButton("Copy")
                cp_btn.setIcon(get_icon("copy", size=12, color=TEXT_MUTED))
                cp_btn.setFixedHeight(26)
                cp_btn.clicked.connect(lambda _, perm=p, b=cp_btn: self._copy_text(b, perm))
                iw_layout.addWidget(cp_btn)

                item = QListWidgetItem()
                item.setSizeHint(item_w.sizeHint())
                list_widget.addItem(item)
                list_widget.setItemWidget(item, item_w)

            if list_widget.count() == 0:
                empty_lbl = QLabel("No permissions match the current filter.")
                empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty_lbl.setProperty("role", "muted")
                item = QListWidgetItem()
                item.setSizeHint(empty_lbl.sizeHint())
                list_widget.addItem(item)
                list_widget.setItemWidget(item, empty_lbl)

        def set_mode(m: str) -> None:
            active_filter["mode"] = m
            btn_all.setChecked(m == "all")
            btn_high.setChecked(m == "high")
            btn_norm.setChecked(m == "norm")
            update_perm_list()

        btn_all.clicked.connect(lambda: set_mode("all"))
        btn_high.clicked.connect(lambda: set_mode("high"))
        btn_norm.clicked.connect(lambda: set_mode("norm"))

        search_input.textChanged.connect(
            lambda txt: [active_filter.update({"query": txt}), update_perm_list()]
        )

        update_perm_list()
        self._perm_layout.addWidget(panel)

    def _refresh_components_panel(self) -> None:
        _clear_layout(self._comp_layout)
        if not self._apk_info:
            return

        panel = QWidget()
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(12)

        acts = self._apk_info.activities
        srvs = self._apk_info.services
        rcvs = self._apk_info.receivers
        prvs = self._apk_info.providers
        total = len(acts) + len(srvs) + len(rcvs) + len(prvs)

        # 4 Stat cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        stats_row.addWidget(StatCard(str(len(acts)), "Activities"))
        stats_row.addWidget(StatCard(str(len(srvs)), "Services"))
        stats_row.addWidget(StatCard(str(len(rcvs)), "Receivers"))
        stats_row.addWidget(StatCard(str(len(prvs)), "Providers"))
        layout.addLayout(stats_row)

        # Search and Category filter row
        cat_row = QHBoxLayout()
        cat_row.setSpacing(8)

        search_input = QLineEdit()
        search_input.setPlaceholderText("Search components by class name...")
        search_input.setClearButtonEnabled(True)
        search_input.setFixedHeight(32)
        cat_row.addWidget(search_input, 1)

        b_all = QPushButton(f"All ({total})")
        b_act = QPushButton(f"Activities ({len(acts)})")
        b_srv = QPushButton(f"Services ({len(srvs)})")
        b_rcv = QPushButton(f"Receivers ({len(rcvs)})")
        b_prv = QPushButton(f"Providers ({len(prvs)})")

        for b in (b_all, b_act, b_srv, b_rcv, b_prv):
            b.setCheckable(True)
            b.setFixedHeight(32)
        b_all.setChecked(True)

        cat_row.addWidget(b_all)
        cat_row.addWidget(b_act)
        cat_row.addWidget(b_srv)
        cat_row.addWidget(b_rcv)
        cat_row.addWidget(b_prv)
        layout.addLayout(cat_row)

        list_widget = QListWidget()
        list_widget.setSpacing(2)
        list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(list_widget, 1)

        light = is_light()
        all_items: list[tuple[str, str, str, str]] = []  # type, color, bg, name
        c_act = "#2563eb" if light else "#3b82f6"
        c_srv = "#7c3aed" if light else "#a855f7"
        c_rcv = "#d97706" if light else "#f59e0b"
        c_prv = "#059669" if light else "#10b981"

        bg_act = "rgba(37, 99, 235, 0.08)" if light else "rgba(59, 130, 246, 0.12)"
        bg_srv = "rgba(124, 58, 237, 0.08)" if light else "rgba(168, 85, 247, 0.12)"
        bg_rcv = "rgba(217, 119, 6, 0.08)" if light else "rgba(245, 158, 11, 0.12)"
        bg_prv = "rgba(5, 150, 105, 0.08)" if light else "rgba(16, 185, 129, 0.12)"

        for a in acts:
            all_items.append(("Activity", c_act, bg_act, a))
        for s in srvs:
            all_items.append(("Service", c_srv, bg_srv, s))
        for r in rcvs:
            all_items.append(("Receiver", c_rcv, bg_rcv, r))
        for p in prvs:
            all_items.append(("Provider", c_prv, bg_prv, p))

        state = {"cat": "all", "query": ""}

        def update_comp_list() -> None:
            list_widget.clear()
            cat = state["cat"]
            query = state["query"].lower().strip()

            for type_name, color, bg, name in all_items:
                if cat != "all" and type_name.lower() != cat:
                    continue
                if query and query not in name.lower():
                    continue

                item_w = QWidget()
                item_w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                iw_layout = QHBoxLayout(item_w)
                iw_layout.setContentsMargins(10, 8, 10, 8)
                iw_layout.setSpacing(10)

                pill = QLabel(type_name.upper())
                pill.setStyleSheet(
                    f"border: 1px solid {color}; color: {color}; background: {bg}; "
                    f"border-radius: 4px; padding: 2px 8px; font-weight: 700; font-size: 10px;"
                )
                pill.setFixedWidth(75)
                iw_layout.addWidget(pill)

                lbl = QLabel(name)
                lbl.setProperty("role", "mono")
                iw_layout.addWidget(lbl, 1)

                cp_btn = QPushButton("Copy")
                cp_btn.setIcon(get_icon("copy", size=12, color=TEXT_MUTED))
                cp_btn.setFixedHeight(26)
                cp_btn.clicked.connect(lambda _, cname=name, b=cp_btn: self._copy_text(b, cname))
                iw_layout.addWidget(cp_btn)

                item = QListWidgetItem()
                item.setSizeHint(item_w.sizeHint())
                list_widget.addItem(item)
                list_widget.setItemWidget(item, item_w)

            if list_widget.count() == 0:
                empty_lbl = QLabel("No components match the current filter.")
                empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty_lbl.setProperty("role", "muted")
                item = QListWidgetItem()
                item.setSizeHint(empty_lbl.sizeHint())
                list_widget.addItem(item)
                list_widget.setItemWidget(item, empty_lbl)

        def set_cat(c: str) -> None:
            state["cat"] = c
            b_all.setChecked(c == "all")
            b_act.setChecked(c == "activity")
            b_srv.setChecked(c == "service")
            b_rcv.setChecked(c == "receiver")
            b_prv.setChecked(c == "provider")
            update_comp_list()

        b_all.clicked.connect(lambda: set_cat("all"))
        b_act.clicked.connect(lambda: set_cat("activity"))
        b_srv.clicked.connect(lambda: set_cat("service"))
        b_rcv.clicked.connect(lambda: set_cat("receiver"))
        b_prv.clicked.connect(lambda: set_cat("provider"))

        search_input.textChanged.connect(
            lambda txt: [state.update({"query": txt}), update_comp_list()]
        )

        update_comp_list()
        self._comp_layout.addWidget(panel)

    def _copy_text(self, btn: QPushButton, text: str, original_label: str = "Copy") -> None:
        QApplication.clipboard().setText(text)
        btn.setText("Copied!")
        btn.setIcon(get_icon("check", size=12, color="#22c55e"))
        QTimer.singleShot(1600, lambda: self._reset_copy_btn(btn, original_label))

    def _reset_copy_btn(self, btn: QPushButton, original_label: str) -> None:
        try:
            btn.setText(original_label)
            btn.setIcon(get_icon("copy", size=12, color=TEXT_MUTED))
        except RuntimeError:
            pass

    def _label(self, text: str, muted: bool = False) -> QLabel:
        label = QLabel(text)
        if muted:
            label.setProperty("role", "dim")
            label.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        return label

    def _divider(self) -> QWidget:
        line = QWidget()
        line.setFixedHeight(1)
        line.setProperty("role", "divider")
        return line

    def set_device(self, device: object) -> None:
        self._active_device = device
