"""APK Analyzer page — Section 6.2. Identity header + Signature, Permissions,
Components, Size, Hosts panels. Populated from `static_data.ANALYZER_APK`;
Phase 2 swaps in `ApkService.inspect()` without changing this layout — panels
still load lazily once full androguard analysis lands.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.ui import static_data
from droiddesk.ui.static_data import ANALYZER_APK
from droiddesk.ui.widgets.card import PageHeader
from droiddesk.ui.widgets.status_pill import TagPill


class AnalyzerPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "APK analyzer", "Everything derivable from the file without installing it."
        )
        header.add_action(QPushButton("⇄  Compare with another APK"))
        open_button = QPushButton("⛁  Open APK")
        open_button.setProperty("role", "primary")
        header.add_action(open_button)
        outer.addWidget(header)

        outer.addWidget(self._build_identity_bar())

        tabs = QTabWidget()
        tabs.addTab(self._build_signature_panel(), "Signature")
        tabs.addTab(self._build_permissions_panel(), "Permissions")
        tabs.addTab(self._build_components_panel(), "Components")
        tabs.addTab(self._build_size_panel(), "Size")
        tabs.addTab(self._build_hosts_panel(), "Hosts")
        outer.addWidget(tabs, 1)

    def _build_identity_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 4)

        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        name = QLabel(ANALYZER_APK.file_path.name)
        name.setStyleSheet("font-size: 15px; font-weight: 700;")
        package = QLabel(ANALYZER_APK.package_name)
        package.setProperty("role", "mono")
        name_col.addWidget(name)
        name_col.addWidget(package)
        layout.addLayout(name_col)
        layout.addStretch(1)

        size_mb = ANALYZER_APK.size_bytes / (1024 * 1024)
        for text in (
            f"{ANALYZER_APK.version_name} ({ANALYZER_APK.version_code})",
            f"min {ANALYZER_APK.min_sdk}",
            f"target {ANALYZER_APK.target_sdk}",
            f"{size_mb:.1f} MB",
            "arm64-v8a",
        ):
            layout.addWidget(TagPill(text))
        return bar

    def _build_signature_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 16, 4, 4)
        layout.setSpacing(16)

        layout.addWidget(self._label("SCHEMES PRESENT", muted=True))
        schemes_row = QHBoxLayout()
        for n in (1, 2, 3, 4):
            present = n in ANALYZER_APK.signature_schemes
            pill = QLabel(f"v{n}")
            color = "#27ae60" if present else "#5c5f66"
            pill.setStyleSheet(
                f"border: 1px solid {color}; color: {color}; border-radius: 3px; "
                f"padding: 2px 10px; font-weight: 700; font-size: 11px;"
            )
            schemes_row.addWidget(pill)
        schemes_row.addStretch(1)
        layout.addLayout(schemes_row)

        layout.addWidget(self._divider())
        layout.addWidget(self._label("CERTIFICATE", muted=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        for row, (key, value) in enumerate(static_data.ANALYZER_CERT.items()):
            key_label = QLabel(key)
            key_label.setProperty("role", "muted")
            key_label.setFixedWidth(90)
            value_label = QLabel(value)
            value_label.setProperty("role", "mono")
            grid.addWidget(key_label, row, 0)
            grid.addWidget(value_label, row, 1)
        layout.addLayout(grid)

        note = QLabel("Read by apksigner verify --print-certs.")
        note.setProperty("role", "muted")
        layout.addWidget(note)
        layout.addStretch(1)
        return panel

    def _build_permissions_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 16, 4, 4)
        list_widget = QListWidget()
        for permission in ANALYZER_APK.permissions:
            short = permission.rsplit(".", 1)[-1]
            flagged = permission in static_data.ANALYZER_HIGH_RISK_PERMISSIONS
            list_widget.addItem(f"{'⚠ ' if flagged else '   '}{short}")
        layout.addWidget(list_widget)
        return panel

    def _build_components_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 16, 4, 4)
        layout.setSpacing(16)

        counts_row = QHBoxLayout()
        for label, count in static_data.ANALYZER_COMPONENT_COUNTS:
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
        for activity in ANALYZER_APK.activities:
            list_widget.addItem(f"activity   {activity}")
        for service in ANALYZER_APK.services:
            list_widget.addItem(f"service    {service}")
        for receiver in ANALYZER_APK.receivers:
            list_widget.addItem(f"receiver   {receiver}")
        for provider in ANALYZER_APK.providers:
            list_widget.addItem(f"provider   {provider}")
        layout.addWidget(list_widget, 1)
        return panel

    def _build_size_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 16, 4, 4)
        table = QTableWidget(len(static_data.ANALYZER_SIZE_BREAKDOWN), 2)
        table.setHorizontalHeaderLabels(["Entry", "Size"])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(1, 100)
        for row, (entry, size) in enumerate(static_data.ANALYZER_SIZE_BREAKDOWN):
            table.setItem(row, 0, QTableWidgetItem(entry))
            table.setItem(row, 1, QTableWidgetItem(size))
        layout.addWidget(table)
        return panel

    def _build_hosts_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 16, 4, 4)
        table = QTableWidget(len(static_data.ANALYZER_HOSTS), 2)
        table.setHorizontalHeaderLabels(["Host", "Note"])
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setColumnWidth(0, 260)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for row, (host, note) in enumerate(static_data.ANALYZER_HOSTS):
            table.setItem(row, 0, QTableWidgetItem(host))
            table.setItem(row, 1, QTableWidgetItem(note))
        layout.addWidget(table)
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
