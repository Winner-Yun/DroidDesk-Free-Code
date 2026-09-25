"""APK Analyzer page inspecting signature, permissions, components, size, and network hosts."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.core.models import ApkInfo
from droiddesk.ui.theme import TEXT_MUTED, get_icon
from droiddesk.ui.widgets.card import PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.status_pill import TagPill

_HIGH_RISK_PERMISSIONS = {
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.SYSTEM_ALERT_WINDOW",
    "android.permission.WRITE_SETTINGS",
    "android.permission.READ_PHONE_STATE",
}


class AnalyzerPage(QWidget):
    upload_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._apk_info: ApkInfo | None = None
        self._full_analysis_loaded = False

        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "APK analyzer", "Everything derivable from the file without installing it."
        )
        outer.addWidget(header)

        self._identity_container = QWidget()
        self._identity_layout = QVBoxLayout(self._identity_container)
        self._identity_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._identity_container)

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._sig_panel = QWidget()
        self._perm_panel = QWidget()
        self._comp_panel = QWidget()

        self._tabs.addTab(
            self._sig_panel, get_icon("award", size=14, color=TEXT_MUTED), "Signature"
        )
        self._tabs.addTab(
            self._perm_panel, get_icon("key-round", size=14, color=TEXT_MUTED), "Permissions"
        )
        self._tabs.addTab(
            self._comp_panel, get_icon("layers", size=14, color=TEXT_MUTED), "Components"
        )

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

    def load_apk(self, path: Path | None) -> None:
        if path is None:
            self._apk_info = None
            self._full_analysis_loaded = False
            self._refresh_ui()
            return
        try:
            self._apk_info = self._ctx.apk_service.inspect(path)
            self._full_analysis_loaded = False
            self._refresh_ui()
            self._on_tab_changed(self._tabs.currentIndex())
        except Exception as e:
            print(f"Error opening APK: {e}")

    def _on_open_apk(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open APK", "", "APK Files (*.apk)")
        if path:
            self.load_apk(Path(path))

    def _on_tab_changed(self, index: int) -> None:
        if not self._apk_info or self._full_analysis_loaded:
            return

        if index in (0, 1, 2):
            try:
                self._apk_info = self._ctx.apk_service.inspect_full(self._apk_info.file_path)
                self._full_analysis_loaded = True
                self._refresh_ui()
            except Exception as e:
                print(f"Error performing full analysis: {e}")

    def _refresh_ui(self) -> None:
        while self._identity_layout.count():
            item = self._identity_layout.takeAt(0)
            if item:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        if self._apk_info:
            self._empty_state.hide()
            self._identity_container.show()
            self._tabs.show()
            self._identity_layout.addWidget(self._build_identity_bar())
        else:
            self._identity_container.hide()
            self._tabs.hide()
            self._empty_state.show()

        if self._apk_info and self._full_analysis_loaded:
            current_idx = self._tabs.currentIndex()
            self._tabs.removeTab(2)
            self._tabs.removeTab(1)
            self._tabs.removeTab(0)

            self._sig_panel = self._build_signature_panel()
            self._perm_panel = self._build_permissions_panel()
            self._comp_panel = self._build_components_panel()

            self._tabs.insertTab(
                0, self._sig_panel, get_icon("award", size=14, color=TEXT_MUTED), "Signature"
            )
            self._tabs.insertTab(
                1, self._perm_panel, get_icon("key-round", size=14, color=TEXT_MUTED), "Permissions"
            )
            self._tabs.insertTab(
                2, self._comp_panel, get_icon("layers", size=14, color=TEXT_MUTED), "Components"
            )
            self._tabs.setCurrentIndex(current_idx)

    def _build_identity_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 4)

        if not self._apk_info:
            return bar

        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        name = QLabel(self._apk_info.file_path.name)
        name.setStyleSheet("font-size: 15px; font-weight: 700;")
        package = QLabel(self._apk_info.package_name)
        package.setProperty("role", "mono")
        name_col.addWidget(name)
        name_col.addWidget(package)
        layout.addLayout(name_col)
        layout.addStretch(1)

        size_mb = self._apk_info.size_bytes / (1024 * 1024)
        for text in (
            f"{self._apk_info.version_name} ({self._apk_info.version_code})",
            f"min {self._apk_info.min_sdk}",
            f"target {self._apk_info.target_sdk}",
            f"{size_mb:.1f} MB",
        ):
            layout.addWidget(TagPill(text))
        return bar

    def _build_signature_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 16, 4, 4)
        layout.setSpacing(16)

        if not self._apk_info:
            return panel

        layout.addWidget(self._label("SCHEMES PRESENT", muted=True))
        schemes_row = QHBoxLayout()
        for n in (1, 2, 3, 31, 4):
            present = n in self._apk_info.signature_schemes
            label_text = f"v{n}" if n != 31 else "v3.1"
            pill = QLabel(label_text)
            color = "#27ae60" if present else "#5c5f66"
            pill.setStyleSheet(
                f"border: 1px solid {color}; color: {color}; border-radius: 3px; "
                f"padding: 2px 10px; font-weight: 700; font-size: 11px;"
            )
            schemes_row.addWidget(pill)

        # Add verification status pill
        is_verified = self._apk_info.signature_verified
        status_pill = QLabel("✓ Verified" if is_verified else "⚠ Unverified")
        status_color = "#27ae60" if is_verified else "#f1c40f"
        status_pill.setStyleSheet(
            f"border: 1px solid {status_color}; color: {status_color}; border-radius: 3px; "
            f"padding: 2px 10px; font-weight: 700; font-size: 11px; margin-left: 12px;"
        )
        schemes_row.addWidget(status_pill)
        schemes_row.addStretch(1)
        layout.addLayout(schemes_row)

        cert_dn = self._apk_info.certificate_dn or ""
        is_debug = "android debug" in cert_dn.lower()
        if is_debug:
            banner = QWidget()
            banner.setStyleSheet(
                "background: rgba(241, 196, 15, 0.1); "
                "border: 1px solid rgba(241, 196, 15, 0.4); "
                "border-radius: 6px; padding: 10px;"
            )
            banner_layout = QVBoxLayout(banner)
            banner_layout.setContentsMargins(10, 8, 10, 8)
            banner_layout.setSpacing(4)
            b_title = QLabel("Android Debug Keystore Signature")
            b_title.setStyleSheet("color: #f1c40f; font-weight: 700; font-size: 12px;")
            b_desc = QLabel(
                "This APK was signed with the default SDK debug key (debug.keystore). "
                "All debug APKs built on this machine share this exact same signature."
            )
            b_desc.setWordWrap(True)
            b_desc.setStyleSheet("color: #cfd3dc; font-size: 12px;")
            banner_layout.addWidget(b_title)
            banner_layout.addWidget(b_desc)
            layout.addWidget(banner)

        layout.addWidget(self._divider())
        layout.addWidget(self._label("CERTIFICATE DETAILS", muted=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)

        row_idx = 0
        if cert_dn:
            key_label = QLabel("Subject / DN")
            key_label.setProperty("role", "muted")
            key_label.setFixedWidth(90)
            value_label = QLabel(cert_dn)
            value_label.setProperty("role", "mono")
            value_label.setWordWrap(True)
            grid.addWidget(key_label, row_idx, 0)
            grid.addWidget(value_label, row_idx, 1)
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
                key_label.setFixedWidth(90)
                value_label = QLabel(fp)
                value_label.setProperty("role", "mono")
                grid.addWidget(key_label, row_idx, 0)
                grid.addWidget(value_label, row_idx, 1)
                row_idx += 1

        layout.addLayout(grid)

        source_tool = self._apk_info.signature_source or "apksigner"
        source_note = (
            "Read by: apksigner verify --print-certs -v"
            if source_tool == "apksigner"
            else "Read by: androguard certificate parser (fallback)"
        )
        note = QLabel(source_note)
        note.setProperty("role", "muted")
        layout.addWidget(note)
        layout.addStretch(1)
        return panel

    def _build_permissions_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 16, 4, 4)

        if not self._apk_info:
            return panel

        list_widget = QListWidget()
        for permission in self._apk_info.permissions:
            short = permission.rsplit(".", 1)[-1]
            flagged = permission in _HIGH_RISK_PERMISSIONS
            list_widget.addItem(f"{'⚠ ' if flagged else '   '}{short}")
        layout.addWidget(list_widget)
        return panel

    def _build_components_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 16, 4, 4)
        layout.setSpacing(16)

        if not self._apk_info:
            return panel

        counts_row = QHBoxLayout()
        counts = [
            ("Activities", len(self._apk_info.activities)),
            ("Services", len(self._apk_info.services)),
            ("Receivers", len(self._apk_info.receivers)),
            ("Providers", len(self._apk_info.providers)),
        ]

        for label, count in counts:
            col = QVBoxLayout()
            value = QLabel(str(count))
            value.setProperty("role", "statNumber")
            caption = QLabel(label)
            caption.setProperty("role", "muted")
            col.addWidget(value)
            col.addWidget(caption)
            counts_row.addLayout(col)
        counts_row.addStretch(1)
        layout.addLayout(counts_row)

        list_widget = QListWidget()
        for activity in self._apk_info.activities:
            list_widget.addItem(f"activity   {activity}")
        for service in self._apk_info.services:
            list_widget.addItem(f"service    {service}")
        for receiver in self._apk_info.receivers:
            list_widget.addItem(f"receiver   {receiver}")
        for provider in self._apk_info.providers:
            list_widget.addItem(f"provider   {provider}")
        layout.addWidget(list_widget, 1)
        return panel

    def _label(self, text: str, muted: bool = False) -> QLabel:
        label = QLabel(text)
        if muted:
            label.setStyleSheet(
                "color: #5c5f66; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
            )
        return label

    def _divider(self) -> QWidget:
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #2c2d33;")
        return line
