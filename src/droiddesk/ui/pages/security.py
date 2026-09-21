"""Security page — Section 6.5/6.6. Severity summary chips, a findings table,
and a detail panel with the recommended action, code view with line highlighting,
and quick action to reveal leaked file locations in File Explorer. Backed by
`FindingsModel` and `ScanService`.
"""

from __future__ import annotations

from pathlib import Path
from typing import override

from PySide6.QtCore import (
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.core.models import Finding
from droiddesk.core.severity import Severity
from droiddesk.infra.scanner.gitleaks_mapping import rule_id_to_key_name
from droiddesk.infra.scanner.util import detect_environment_info
from droiddesk.services.scan_service import ScanService
from droiddesk.ui.models.findings_model import FindingsModel
from droiddesk.ui.widgets.card import PageHeader
from droiddesk.ui.widgets.code_view import CodeView
from droiddesk.ui.widgets.empty_state import EmptyStateWidget
from droiddesk.ui.widgets.severity_badge import SeverityBadge

_SUMMARY_CHIP_SPECS: list[tuple[str, Severity]] = [
    ("Critical", Severity.CRITICAL),
    ("High", Severity.HIGH),
    ("Needs review", Severity.NEEDS_REVIEW),
    ("Informational", Severity.INFORMATIONAL),
]

_SEVERITY_TEXT_COLOR = {
    Severity.CRITICAL: "#e0574a",
    Severity.HIGH: "#e67e22",
    Severity.NEEDS_REVIEW: "#f1c40f",
    Severity.INFORMATIONAL: "#8b8e94",
}

_SEVERITY_RECOMMENDATIONS = {
    "android-service-account-json": (
        "Revoke this service account key in Google Cloud Console immediately. "
        "Move backend operations to a secure server."
    ),
    "android-signing-key": (
        "Remove signing keystore from git tracking. Store keystore outside repository "
        "and inject via secure CI environment variables."
    ),
    "android-env-backend-secret": (
        "Remove backend environment variables from client tree. Never bundle database "
        "passwords or server secrets."
    ),
    "android-firebase-legacy-token": (
        "Revoke legacy database token in Firebase Console. Migrate to Firebase Authentication "
        "and security rules."
    ),
    "android-maps-api-key": (
        "Restrict this key in Google Cloud Console by Android application package name "
        "and SHA-1 certificate fingerprint."
    ),
    "firebase-api-key": (
        "Restrict this Firebase API key in Google Cloud Console by Android application "
        "package name and SHA-1 certificate fingerprint, and limit to enabled APIs."
    ),
    "google-api-key": (
        "Restrict this Google API key in Google Cloud Console by Android application "
        "package name and SHA-1 certificate fingerprint."
    ),
    "android-google-services-json": (
        "Normal client configuration file. Ensure no private service account keys are embedded."
    ),
    "aws-access-key-id": (
        "Revoke AWS access key in AWS IAM Console immediately and audit CloudTrail logs."
    ),
    "generic-private-key-pem": (
        "Revoke private key and generate a new keypair. Never commit private keys."
    ),
    "high-entropy-credential-string": (
        "Review whether this string contains a sensitive credential, token, or password."
    ),
}


class SecurityFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._severity_filter: Severity | None = None

    def set_severity_filter(self, severity: Severity | None) -> None:
        self._severity_filter = severity
        self.invalidateFilter()

    @override
    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        model = self.sourceModel()
        if not isinstance(model, FindingsModel):
            return True
        finding = model.finding_at(source_row)
        return not (self._severity_filter is not None and finding.severity != self._severity_filter)


class SecurityPage(QWidget):
    upload_requested = Signal()
    findings_changed = Signal(int)

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._apk_path: Path | None = None
        self._active_finding: Finding | None = None

        self._scan_service = getattr(ctx, "scan_service", None) or ScanService(ctx.tool_locator)
        self._scan_service.finished.connect(self._on_scan_finished)
        self._scan_service.failed.connect(self._on_scan_failed)
        self._scan_service.cancelled.connect(self._on_scan_cancelled)

        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "Secret scanner",
            "Detects accidental exposure, not deliberate concealment. "
            "Click 'Scan project' to inspect your workspace repository "
            "or active APK for credentials.",
        )
        self._scan_button = QPushButton("Scan project")
        self._scan_button.setProperty("role", "primary")
        self._scan_button.clicked.connect(self._on_scan_clicked)
        header.add_action(self._scan_button)
        outer.addWidget(header)

        self._empty_banner = EmptyStateWidget(
            title="No Active APK Selected",
            message=(
                "Secret scanning runs against repository source files. To inspect "
                "credential exposures inside an APK archive, select or upload an APK."
            ),
            button_text="Upload APK",
            compact=True,
        )
        self._empty_banner.upload_requested.connect(self.upload_requested.emit)
        outer.addWidget(self._empty_banner)

        # Summary chips row
        self._summary_chips: dict[Severity, QLabel] = {}
        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)

        for label, severity in _SUMMARY_CHIP_SPECS:
            chip_widget, count_label = self._create_summary_chip(label, severity, 0)
            summary_row.addWidget(chip_widget)
            self._summary_chips[severity] = count_label

        summary_row.addStretch(1)
        outer.addLayout(summary_row)

        # Table backed by FindingsModel and SecurityFilterProxyModel
        self._model = FindingsModel()
        self._proxy = SecurityFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("securitySplitter")
        self._splitter.setStyleSheet("QSplitter::handle {    background: #23252a;    width: 3px;}")

        self._table = self._build_table()
        self._splitter.addWidget(self._table)

        # Detail panel starts empty
        self._detail = self._build_detail(None)
        self._splitter.addWidget(self._detail)

        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([640, 400])
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)

        outer.addWidget(self._splitter, 1)

        # Initial findings start empty — only populate on scan
        self._model.set_findings([])
        self._update_summary_chips()

        self.set_apk(None)

    def set_apk(self, path: Path | None) -> None:
        self._apk_path = path
        if path is None:
            self._empty_banner.show()
            self._scan_button.setText("Scan project")
        else:
            self._empty_banner.hide()
            self._scan_button.setText(f"Scan APK ({path.name})")

    def _create_summary_chip(
        self, label: str, severity: Severity, count: int
    ) -> tuple[QWidget, QLabel]:
        chip = QFrame()
        chip.setProperty("role", "card")
        layout = QHBoxLayout(chip)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)
        color = _SEVERITY_TEXT_COLOR[severity]
        count_label = QLabel(str(count))
        count_label.setStyleSheet(f"color: {color}; font-weight: 800; font-size: 15px;")
        text_label = QLabel(label)
        text_label.setProperty("role", "muted")
        layout.addWidget(count_label)
        layout.addWidget(text_label)

        btn = QPushButton()
        btn.setStyleSheet("background: transparent; border: none;")
        btn.clicked.connect(lambda: self._on_chip_clicked(severity))

        # Make chip clickable
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.mousePressEvent = lambda _e: self._on_chip_clicked(severity)  # type: ignore[method-assign]
        return chip, count_label

    def _on_chip_clicked(self, severity: Severity) -> None:
        # Toggle severity filter
        if self._proxy._severity_filter == severity:
            self._proxy.set_severity_filter(None)
        else:
            self._proxy.set_severity_filter(severity)

    def _build_table(self) -> QTableView:
        table = QTableView()
        table.setModel(self._proxy)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(0, 70)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(1, 160)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(2, 120)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(3, 90)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(4, 40)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        table.setStyleSheet(
            "QTableView {"
            "    outline: 0;"
            "    border: 1px solid #26282f;"
            "    border-radius: 8px;"
            "    background: #18191c;"
            "}"
            "QTableView::item {"
            "    padding: 8px 6px;"
            "    border-bottom: 1px solid #22242a;"
            "}"
            "QTableView::item:selected {"
            "    background: #2a313d;"
            "    color: #ffffff;"
            "}"
            "QHeaderView::section {"
            "    background: #1e1f24;"
            "    color: #8b8e94;"
            "    padding: 9px 6px;"
            "    border: none;"
            "    border-bottom: 1px solid #2d3038;"
            "    font-weight: 700;"
            "    font-size: 11px;"
            "}"
        )

        table.selectionModel().selectionChanged.connect(self._on_table_selection_changed)
        table.doubleClicked.connect(self._on_table_double_clicked)
        return table

    def _on_table_selection_changed(self) -> None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return
        source_idx = self._proxy.mapToSource(indexes[0])
        finding = self._model.finding_at(source_idx.row())
        self._update_detail_panel(finding)

    def _on_table_double_clicked(self, index: QModelIndex) -> None:
        source_idx = self._proxy.mapToSource(index)
        finding = self._model.finding_at(source_idx.row())
        self._on_open_file_location(finding)

    def _update_detail_panel(self, finding: Finding | None) -> None:
        sizes = self._splitter.sizes()
        new_detail = self._build_detail(finding)
        self._splitter.replaceWidget(1, new_detail)
        self._detail.deleteLater()
        self._detail = new_detail
        if sizes and sum(sizes) > 0 and sizes[1] > 150:
            self._splitter.setSizes(sizes)
        else:
            self._splitter.setSizes([640, 420])

    def _resolve_finding_file_path(self, file_path: Path) -> Path:
        if file_path.is_file() or file_path.is_dir():
            return file_path.resolve()
        if self._apk_path is not None:
            apk_extracted = self._apk_path.parent / f"{self._apk_path.stem}_extracted"
            cand_apk = apk_extracted / file_path
            if cand_apk.exists():
                return cand_apk.resolve()
            import tempfile

            tmp_dir = Path(tempfile.gettempdir()) / "droiddesk_extracted" / self._apk_path.stem
            tmp_extracted = tmp_dir / file_path
            if tmp_extracted.exists():
                return tmp_extracted.resolve()

        if file_path.name == "resources.arsc":
            candidates = [
                file_path.parent / "res" / "values" / "strings.xml",
                file_path.parent.parent
                / f"{file_path.parent.stem}_extracted"
                / "res"
                / "values"
                / "strings.xml",
                Path.cwd() / "res" / "values" / "strings.xml",
            ]
            for cand in candidates:
                if cand.is_file():
                    return cand.resolve()
        cwd_candidate = (Path.cwd() / file_path).resolve()
        if cwd_candidate.exists():
            return cwd_candidate
        return file_path

    def _on_open_file_location(self, finding: Finding) -> None:
        target = self._resolve_finding_file_path(finding.file_path)
        p = target
        while not p.exists() and p != p.parent:
            p = p.parent

        folder_to_open = p.parent if p.is_file() else p
        if folder_to_open.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_to_open)))
        else:
            QMessageBox.information(
                self,
                "File Location",
                f"File location:\n{target.as_posix()}\n\nFolder does not exist on disk.",
            )

    def _on_copy_path(self, path_text: str, button: QPushButton) -> None:
        QGuiApplication.clipboard().setText(path_text)
        orig_text = button.text()
        button.setText("Copied!")
        QTimer.singleShot(1500, lambda: button.setText(orig_text))

    def _extract_line_content(self, path: Path, line_number: int | None) -> str | None:
        if line_number is None or not path.is_file():
            return None
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if 1 <= line_number <= len(lines):
                return lines[line_number - 1].strip()
        except Exception:
            pass
        return None

    def _build_detail(self, finding: Finding | None) -> QWidget:
        self._active_finding = finding

        scroll = QScrollArea()
        scroll.setObjectName("detailScroll")
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(390)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "#detailScroll {"
            "    background: #18191c;"
            "    border: 1px solid #282a30;"
            "    border-radius: 8px;"
            "}"
            "#detailScroll > QWidget > QWidget {"
            "    background: transparent;"
            "}"
        )

        card = QWidget()
        card.setStyleSheet("background: transparent;")
        card.setMinimumWidth(320)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        if finding is None:
            empty_msg = QLabel(
                "No finding selected.\n\n"
                "Click 'Scan project' above to scan your project workspace for secrets, "
                "or select a finding from the table to inspect details."
            )
            empty_msg.setProperty("role", "muted")
            empty_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_msg.setWordWrap(True)
            layout.addWidget(empty_msg)
            scroll.setWidget(card)
            return scroll

        env_tag, env_desc = detect_environment_info(finding.file_path, finding.rule_id)
        resolved_path = self._resolve_finding_file_path(finding.file_path)

        btn_style = (
            "QPushButton {"
            "    background: #23252b;"
            "    border: 1px solid #363942;"
            "    border-radius: 4px;"
            "    padding: 3px 8px;"
            "    font-size: 11px;"
            "    font-weight: 600;"
            "    color: #d1d5db;"
            "}"
            "QPushButton:hover {"
            "    background: #2c2f38;"
            "    border-color: #5b9bd5;"
            "    color: #ffffff;"
            "}"
        )

        # Top row: Severity badge & Environment pill badge
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        top_row.addWidget(SeverityBadge(finding.severity))

        env_badge = QLabel(env_tag)
        env_badge.setStyleSheet(
            "background: rgba(167, 139, 250, 0.15); color: #c4b5fd; "
            "border: 1px solid rgba(167, 139, 250, 0.35); border-radius: 4px; "
            "padding: 2px 8px; font-size: 11px; font-weight: 600;"
        )
        env_badge.setToolTip(env_desc)
        top_row.addWidget(env_badge)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        key_name = rule_id_to_key_name(finding.rule_id)
        key_lbl = QLabel(key_name)
        key_lbl.setStyleSheet(
            "color: #f3f4f6; font-size: 13px; font-weight: 700; "
            "font-family: 'Cascadia Mono', Consolas, monospace;"
        )
        key_lbl.setToolTip(f"Rule ID: {finding.rule_id}")
        layout.addWidget(key_lbl)

        # Section 1: Location & Environment
        layout.addWidget(self._section_label("LOCATION & ENVIRONMENT"))

        meta_box = QFrame()
        meta_box.setObjectName("locBox")
        meta_box.setStyleSheet(
            "#locBox {"
            "    background: #16171a;"
            "    border: 1px solid #282a30;"
            "    border-radius: 6px;"
            "}"
            "#locBox QLabel {"
            "    background: transparent;"
            "    border: none;"
            "}"
        )
        meta_layout = QVBoxLayout(meta_box)
        meta_layout.setContentsMargins(12, 10, 12, 10)
        meta_layout.setSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnMinimumWidth(0, 80)

        # Environment row
        lbl_env = QLabel("Environment:")
        lbl_env.setStyleSheet("color: #9ca3af; font-size: 11px;")
        val_env = QLabel(env_desc)
        val_env.setStyleSheet("color: #c4b5fd; font-size: 11px; font-weight: 600;")
        grid.addWidget(lbl_env, 0, 0)
        grid.addWidget(val_env, 0, 1)

        # File row
        lbl_file = QLabel("File:")
        lbl_file.setStyleSheet("color: #9ca3af; font-size: 11px;")
        display_name = (
            "strings.xml" if finding.file_path.name == "resources.arsc" else finding.file_path.name
        )
        val_file = QLabel(display_name)
        val_file.setStyleSheet("color: #f3f4f6; font-size: 12px; font-weight: 700;")
        grid.addWidget(lbl_file, 1, 0)
        grid.addWidget(val_file, 1, 1)

        # Line row
        lbl_line = QLabel("Line:")
        lbl_line.setStyleSheet("color: #9ca3af; font-size: 11px;")
        line_str = (
            f"Line {finding.line_number}" if finding.line_number is not None else "File-level"
        )
        val_line = QLabel(line_str)
        if finding.line_number is not None:
            val_line.setStyleSheet(
                "background: #3b2816; color: #fbbf24; font-size: 11px; font-weight: 700; "
                "border: 1px solid #78350f; border-radius: 4px; padding: 1px 8px;"
            )
        else:
            val_line.setStyleSheet(
                "background: #23252a; color: #9ca3af; font-size: 11px; font-weight: 600; "
                "border-radius: 4px; padding: 1px 8px;"
            )
        line_row = QHBoxLayout()
        line_row.addWidget(val_line)
        line_row.addStretch(1)
        grid.addWidget(lbl_line, 2, 0)
        grid.addLayout(line_row, 2, 1)

        meta_layout.addLayout(grid)

        # Full Path row
        full_path_str = (
            f"{resolved_path.as_posix()}:{finding.line_number}"
            if finding.line_number
            else resolved_path.as_posix()
        )
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        path_edit = QLineEdit(full_path_str)
        path_edit.setReadOnly(True)
        path_edit.setCursorPosition(0)
        path_edit.setToolTip(full_path_str)
        path_edit.setStyleSheet(
            "QLineEdit {"
            "    background: #111215;"
            "    border: 1px solid #282a30;"
            "    border-radius: 4px;"
            "    color: #93c5fd;"
            "    font-family: 'Cascadia Mono', Consolas, monospace;"
            "    font-size: 11px;"
            "    padding: 4px 8px;"
            "}"
            "QLineEdit:focus {"
            "    border-color: #3b82f6;"
            "}"
        )
        path_row.addWidget(path_edit, 1)

        copy_path_btn = QPushButton("Copy path")
        copy_path_btn.setStyleSheet(btn_style)
        copy_path_btn.clicked.connect(lambda: self._on_copy_path(full_path_str, copy_path_btn))
        path_row.addWidget(copy_path_btn)

        meta_layout.addLayout(path_row)
        layout.addWidget(meta_box)

        # Section 2: Key / Token value (Full View)
        layout.addWidget(self._section_label("KEY / TOKEN VALUE (FULL VIEW)"))
        self._add_fallback_content_box(layout, finding.redacted)

        # Section 3: Code Context
        if resolved_path.is_file() and finding.line_number is not None:
            try:
                code_header_row = QHBoxLayout()
                code_header_row.addWidget(
                    self._section_label(f"CODE CONTEXT (LINE {finding.line_number})")
                )
                code_header_row.addStretch(1)

                line_code = self._extract_line_content(resolved_path, finding.line_number)
                if line_code:
                    cp_line_btn = QPushButton("Copy line")
                    cp_line_btn.setStyleSheet(btn_style)
                    cp_line_btn.clicked.connect(lambda: self._on_copy_path(line_code, cp_line_btn))
                    code_header_row.addWidget(cp_line_btn)
                layout.addLayout(code_header_row)

                code_view = CodeView()
                code_view.setFixedHeight(145)
                file_text = resolved_path.read_text(encoding="utf-8", errors="replace")
                code_view.set_text(
                    file_text,
                    highlight_line=finding.line_number,
                    token=finding.redacted,
                )
                layout.addWidget(code_view)
            except Exception:
                pass

        else:
            line_code = self._extract_line_content(resolved_path, finding.line_number)
            if line_code:
                layout.addWidget(self._section_label("LEAKED CODE LINE"))
                line_box = QFrame()
                line_box.setObjectName("lineBox")
                line_box.setStyleSheet(
                    "#lineBox {"
                    "    background: #16171a;"
                    "    border: 1px solid #332527;"
                    "    border-left: 3px solid #e0574a;"
                    "    border-radius: 4px;"
                    "}"
                    "#lineBox QLabel {"
                    "    background: transparent;"
                    "    border: none;"
                    "}"
                )
                line_box_layout = QVBoxLayout(line_box)
                line_box_layout.setContentsMargins(10, 8, 10, 8)
                line_box_layout.setSpacing(6)

                line_text_lbl = QLabel(f"Line {finding.line_number}:  {line_code}")
                line_text_lbl.setStyleSheet("color: #f3f4f6; font-size: 11px;")
                line_text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                line_text_lbl.setWordWrap(True)
                line_box_layout.addWidget(line_text_lbl)

                line_btn_row = QHBoxLayout()
                copy_line_btn = QPushButton("Copy line")
                copy_line_btn.setStyleSheet(btn_style)
                copy_line_btn.clicked.connect(lambda: self._on_copy_path(line_code, copy_line_btn))
                line_btn_row.addWidget(copy_line_btn)
                line_btn_row.addStretch(1)
                line_box_layout.addLayout(line_btn_row)

                layout.addWidget(line_box)

        # Section 4: Recommended Action
        layout.addWidget(self._section_label("RECOMMENDED ACTION"))
        rec_box = QFrame()
        rec_box.setObjectName("recBox")
        rec_box.setStyleSheet(
            "#recBox {"
            "    background: rgba(91, 155, 213, 0.08);"
            "    border: 1px solid rgba(91, 155, 213, 0.25);"
            "    border-left: 3px solid #5b9bd5;"
            "    border-radius: 4px;"
            "}"
            "#recBox QLabel {"
            "    background: transparent;"
            "    border: none;"
            "}"
        )
        r_layout = QVBoxLayout(rec_box)
        r_layout.setContentsMargins(10, 8, 10, 8)
        rec_text = _SEVERITY_RECOMMENDATIONS.get(
            finding.rule_id,
            "Inspect credential usage. If valid and sensitive, revoke and remove from repository.",
        )
        action_label = QLabel(rec_text)
        action_label.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        action_label.setWordWrap(True)
        r_layout.addWidget(action_label)
        layout.addWidget(rec_box)

        layout.addStretch(1)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        reveal_btn = QPushButton("Show in File Explorer")
        reveal_btn.setStyleSheet(
            "QPushButton {"
            "    background: #3b82f6;"
            "    border: 1px solid #2563eb;"
            "    border-radius: 5px;"
            "    padding: 7px 16px;"
            "    font-size: 12px;"
            "    font-weight: 700;"
            "    color: #ffffff;"
            "}"
            "QPushButton:hover {"
            "    background: #2563eb;"
            "}"
        )
        reveal_btn.clicked.connect(lambda: self._on_open_file_location(finding))
        bottom_row.addWidget(reveal_btn)
        layout.addLayout(bottom_row)

        scroll.setWidget(card)
        return scroll

    def _add_fallback_content_box(self, layout: QVBoxLayout, content: str) -> None:
        content_box = QFrame()
        content_box.setObjectName("tokenBox")
        content_box.setStyleSheet(
            "#tokenBox {"
            "    background: #16171a;"
            "    border: 1px solid #282a30;"
            "    border-radius: 6px;"
            "}"
            "#tokenBox QLabel {"
            "    background: transparent;"
            "    border: none;"
            "}"
        )
        content_layout = QVBoxLayout(content_box)
        content_layout.setContentsMargins(12, 10, 12, 10)
        content_layout.setSpacing(6)
        matched = QLabel(content)
        matched.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        matched.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: 600;")
        matched.setWordWrap(True)
        content_layout.addWidget(matched)

        btn_style = (
            "QPushButton {"
            "    background: #23252b;"
            "    border: 1px solid #363942;"
            "    border-radius: 4px;"
            "    padding: 4px 10px;"
            "    font-size: 11px;"
            "    font-weight: 600;"
            "    color: #d1d5db;"
            "}"
            "QPushButton:hover {"
            "    background: #2c2f38;"
            "    border-color: #5b9bd5;"
            "    color: #ffffff;"
            "}"
        )
        tok_btn_row = QHBoxLayout()
        cp_tok_btn = QPushButton("Copy token")
        cp_tok_btn.setStyleSheet(btn_style)
        cp_tok_btn.clicked.connect(lambda: self._on_copy_path(content, cp_tok_btn))
        tok_btn_row.addWidget(cp_tok_btn)
        tok_btn_row.addStretch(1)
        content_layout.addLayout(tok_btn_row)

        layout.addWidget(content_box)

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            "color: #6b7280; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; margin-top: 4px;"
        )
        return label

    def _on_scan_clicked(self) -> None:
        self._scan_button.setEnabled(False)
        self._scan_button.setText("Scanning...")

        # If an active APK is selected, scan the APK; otherwise scan project root
        if self._apk_path is not None and self._apk_path.is_file():
            try:
                self._scan_service.scan_apk_async(self._apk_path)
            except Exception:
                result = self._scan_service.scan_apk(self._apk_path)
                self._on_scan_finished(result)
        else:
            root = Path.cwd()
            try:
                self._scan_service.scan_project_async(root)
            except Exception:
                result = self._scan_service.scan_project(root)
                self._on_scan_finished(result)

    def _on_scan_finished(self, result: object) -> None:
        self._scan_button.setEnabled(True)
        btn_text = f"Scan APK ({self._apk_path.name})" if self._apk_path else "Scan project"
        self._scan_button.setText(btn_text)

        from droiddesk.core.models import ScanResult

        if isinstance(result, ScanResult):
            self._model.set_findings(result.findings)
            self._update_summary_chips()
            self.findings_changed.emit(len(result.findings))
            if self._proxy.rowCount() > 0:
                self._table.selectRow(0)
            else:
                self._update_detail_panel(None)

    def _on_scan_failed(self, error_msg: str) -> None:
        self._scan_button.setEnabled(True)
        btn_text = f"Scan APK ({self._apk_path.name})" if self._apk_path else "Scan project"
        self._scan_button.setText(btn_text)
        QMessageBox.warning(
            self,
            "Scan Failed",
            f"An error occurred while scanning:\n{error_msg}",
        )

    def _on_scan_cancelled(self) -> None:
        self._scan_button.setEnabled(True)
        btn_text = f"Scan APK ({self._apk_path.name})" if self._apk_path else "Scan project"
        self._scan_button.setText(btn_text)

    def _update_summary_chips(self) -> None:
        findings = self._model.findings()
        counts = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 0,
            Severity.NEEDS_REVIEW: 0,
            Severity.INFORMATIONAL: 0,
        }
        for f in findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1

        for sev, count_label in self._summary_chips.items():
            count_label.setText(str(counts.get(sev, 0)))
