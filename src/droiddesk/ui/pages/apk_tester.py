"""APK Tester page — Section 6.3. Artifact-under-test drop zone, the run
sequence checklist, and the verdict panel. Populated from
`static_data.TEST_RUN_STEPS`; Phase 3 swaps the static rows for
`ApkService.step_started` / `step_finished` / `test_complete` without
changing this three-column layout.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.ui import static_data
from droiddesk.ui.static_data import ANALYZER_APK
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.status_pill import StatusIcon


class ApkTesterPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader("Test runner", "Install, launch, observe, capture, clean up — the same sequence every time, against the device you choose.")
        header.actions.addWidget(QLabel("Profile"))
        profile_combo = QComboBox()
        profile_combo.addItem(static_data.TEST_PROFILE_NAME)
        profile_combo.setFixedWidth(140)
        header.add_action(profile_combo)
        header.actions.addWidget(QLabel("Device"))
        device_input = QLineEdit()
        device_input.setFixedWidth(160)
        header.add_action(device_input)
        header.add_action(QPushButton("☐  Cancel"))
        run_button = QPushButton("Run test")
        run_button.setProperty("role", "primary")
        header.add_action(run_button)
        outer.addWidget(header)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        columns.addWidget(self._build_artifact_panel(), 1)
        columns.addWidget(self._build_sequence_panel(), 2)
        columns.addWidget(self._build_verdict_panel(), 1)
        outer.addLayout(columns, 1)

    def _build_artifact_panel(self) -> QWidget:
        card = Card("Artifact under test")
        layout = card.body_layout()

        dropzone = QFrame()
        dropzone.setProperty("role", "card")
        dropzone.setFixedHeight(90)
        dz_layout = QVBoxLayout(dropzone)
        hint = QLabel("Drop an .apk or .aab here, or browse")
        hint.setProperty("role", "muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        dz_layout.addWidget(hint)
        layout.addWidget(dropzone)

        name = QLabel(ANALYZER_APK.file_path.name)
        name.setStyleSheet("font-weight: 600;")
        package = QLabel(ANALYZER_APK.package_name)
        package.setProperty("role", "mono")
        layout.addWidget(name)
        layout.addWidget(package)

        tags_row = QHBoxLayout()
        for text in (
            f"{ANALYZER_APK.version_name} ({ANALYZER_APK.version_code})",
            f"min {ANALYZER_APK.min_sdk}",
            f"target {ANALYZER_APK.target_sdk}",
        ):
            tag = QLabel(text)
            tag.setStyleSheet(
                "border: 1px solid #35373e; color: #8b8e94; border-radius: 3px; "
                "padding: 2px 8px; font-size: 11px;"
            )
            tags_row.addWidget(tag)
        tags_row.addStretch(1)
        layout.addLayout(tags_row)

        note = QLabel(static_data.TEST_RUN_NOTE)
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        layout.addWidget(note)
        layout.addStretch(1)
        return card

    def _build_sequence_panel(self) -> QWidget:
        card = Card("Run sequence")
        layout = card.body_layout()
        for step in static_data.TEST_RUN_STEPS:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(StatusIcon(step.status))

            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            headline_row = QHBoxLayout()
            headline_row.setSpacing(8)
            name_label = QLabel(step.name)
            name_label.setStyleSheet("font-weight: 600;")
            headline_row.addWidget(name_label)
            headline_color = {"pass": "#27ae60", "warn": "#f1c40f", "fail": "#e0574a"}[step.status]
            headline_label = QLabel(step.headline)
            headline_label.setStyleSheet(f"color: {headline_color};")
            headline_row.addWidget(headline_label)
            headline_row.addStretch(1)
            text_col.addLayout(headline_row)

            command_label = QLabel(step.command)
            command_label.setProperty("role", "mono")
            command_label.setStyleSheet("color: #5c5f66; font-family: 'Cascadia Mono'; font-size: 11px;")
            text_col.addWidget(command_label)
            row.addLayout(text_col, 1)

            duration = QLabel(f"{step.duration_ms} ms")
            duration.setProperty("role", "muted")
            row.addWidget(duration)

            layout.addLayout(row)
        layout.addStretch(1)
        return card

    def _build_verdict_panel(self) -> QWidget:
        card = Card("Verdict")
        layout = card.body_layout()

        verdict_color = {"PASS": "#27ae60", "FAIL": "#e0574a"}.get(static_data.TEST_RUN_VERDICT, "#f1c40f")
        verdict = QLabel(static_data.TEST_RUN_VERDICT)
        verdict.setStyleSheet(f"color: {verdict_color}; font-size: 22px; font-weight: 800;")
        layout.addWidget(verdict)

        detail = QLabel(static_data.TEST_RUN_VERDICT_DETAIL)
        detail.setWordWrap(True)
        detail.setProperty("role", "muted")
        layout.addWidget(detail)

        captured_label = QLabel("CAPTURED")
        captured_label.setStyleSheet("color: #5c5f66; font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-top: 8px;")
        layout.addWidget(captured_label)

        capture_box = QFrame()
        capture_box.setProperty("role", "card")
        capture_box.setFixedHeight(120)
        capture_layout = QVBoxLayout(capture_box)
        pending = QLabel("Screenshot pending")
        pending.setProperty("role", "muted")
        pending.setAlignment(Qt.AlignmentFlag.AlignCenter)
        capture_layout.addWidget(pending)
        layout.addWidget(capture_box)

        open_report = QPushButton("▤  Open report")
        open_report.setProperty("role", "link")
        layout.addWidget(open_report)

        layout.addStretch(1)
        return card
