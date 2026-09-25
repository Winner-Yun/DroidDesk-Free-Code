"""APK Tester page providing automated test runner steps, logs, and crash analysis."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import (
    QDesktopServices,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.core.models import ApkInfo, Device, TestRun
from droiddesk.core.profiles import TestProfile
from droiddesk.core.severity import Verdict
from droiddesk.services.apk_service import ApkService
from droiddesk.ui.theme import TEXT_MUTED, get_icon, get_pixmap
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.device_selector import DeviceSelector
from droiddesk.ui.widgets.empty_state import EmptyStateWidget


class StepRowWidget(QWidget):
    """A single test step row that updates in-place during the test run."""

    def __init__(self, step_key: str, title: str, command: str) -> None:
        super().__init__()
        self.step_key = step_key

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(get_pixmap("circle", size=14, color="#5c5f66"))
        row.addWidget(self.icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        headline_row = QHBoxLayout()
        headline_row.setSpacing(8)

        self.name_label = QLabel(title)
        self.name_label.setStyleSheet("font-weight: 600;")
        headline_row.addWidget(self.name_label)

        self.headline_label = QLabel("Pending")
        self.headline_label.setStyleSheet("color: #5c5f66;")
        headline_row.addWidget(self.headline_label)
        headline_row.addStretch(1)
        text_col.addLayout(headline_row)

        self.command_label = QLabel(command)
        self.command_label.setProperty("role", "mono")
        self.command_label.setStyleSheet(
            "color: #5c5f66; font-family: 'Cascadia Mono'; font-size: 11px;"
        )
        text_col.addWidget(self.command_label)
        row.addLayout(text_col, 1)

        self.duration_label = QLabel("-")
        self.duration_label.setProperty("role", "muted")
        row.addWidget(self.duration_label)

    def set_running(self) -> None:
        self.icon_label.setPixmap(get_pixmap("play", size=14, color="#3b82f6"))
        self.headline_label.setText("Running...")
        self.headline_label.setStyleSheet("color: #3b82f6;")

    def set_finished(
        self, passed: bool, duration_ms: int | None = None, detail: str | None = None
    ) -> None:
        if passed:
            self.icon_label.setPixmap(get_pixmap("circle-check", size=14, color="#27ae60"))
            self.headline_label.setText(detail or "Success")
            self.headline_label.setStyleSheet("color: #27ae60;")
        else:
            self.icon_label.setPixmap(get_pixmap("circle-x", size=14, color="#e0574a"))
            self.headline_label.setText(detail or "Failed")
            self.headline_label.setStyleSheet("color: #e0574a;")

        if duration_ms is not None:
            self.duration_label.setText(f"{duration_ms} ms")

    def reset(self) -> None:
        self.icon_label.setPixmap(get_pixmap("circle", size=14, color="#5c5f66"))
        self.headline_label.setText("Pending")
        self.headline_label.setStyleSheet("color: #5c5f66;")
        self.duration_label.setText("-")


class TestWorker(QThread):
    """Executes the test run off the UI thread to keep the interface responsive."""

    def __init__(
        self,
        apk_service: ApkService,
        apk_path: Path,
        device_serial: str,
        profile: TestProfile,
        output_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = apk_service
        self._apk_path = apk_path
        self._device_serial = device_serial
        self._profile = profile
        self._output_dir = output_dir

    def run(self) -> None:
        self._service.run_test(
            apk_path=self._apk_path,
            device_serial=self._device_serial,
            profile=self._profile,
            output_dir=self._output_dir,
        )


class ApkTesterPage(QWidget):
    """Page coordinating the complete automated APK test workflow."""

    upload_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._profile = TestProfile(name="Default")
        self._apk_path: Path | None = None
        self._apk_info: ApkInfo | None = None
        self._step_widgets: dict[str, StepRowWidget] = {}
        self._last_run: TestRun | None = None
        self._worker: TestWorker | None = None

        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "Test runner",
            "Install, launch, observe, capture, clean up - the same sequence every time, "
            "against the device you choose.",
        )

        header.add_action(QLabel("Profile"))
        self._profile_combo = QComboBox()
        self._profile_combo.addItem(self._profile.name)
        self._profile_combo.setFixedWidth(140)
        header.add_action(self._profile_combo)

        header.add_action(QLabel("Device"))
        self._device_selector = DeviceSelector()
        self._device_selector.setFixedWidth(200)
        header.add_action(self._device_selector)

        # Wire device selector to DeviceService
        self._ctx.device_service.devices_changed.connect(self._on_devices_changed)
        devs = getattr(self._ctx.device_service, "_devices", None)
        if devs is None and hasattr(self._ctx.device_service, "devices"):
            try:
                res = self._ctx.device_service.devices()
                if isinstance(res, list):
                    devs = res
            except Exception:
                pass
        self._device_selector.set_devices(devs or [])
        self._device_selector.device_selected.connect(self._update_button_states)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setIcon(get_icon("square", size=13, color=TEXT_MUTED))
        self._cancel_button.setIconSize(QSize(13, 13))
        self._cancel_button.clicked.connect(self._on_cancel)
        header.add_action(self._cancel_button)

        self._run_button = QPushButton("Run test")
        self._run_button.setProperty("role", "primary")
        self._run_button.setIcon(get_icon("play", size=14, color="#ffffff"))
        self._run_button.setIconSize(QSize(14, 14))
        self._run_button.clicked.connect(self._on_run_test)
        header.add_action(self._run_button)

        outer.addWidget(header)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        columns.addWidget(self._build_artifact_panel(), 1)
        columns.addWidget(self._build_sequence_panel(), 2)
        columns.addWidget(self._build_verdict_panel(), 1)
        outer.addLayout(columns, 1)

        # Connect ApkService signals
        self._ctx.apk_service.step_started.connect(self._on_step_started)
        self._ctx.apk_service.step_finished.connect(self._on_step_finished)
        self._ctx.apk_service.test_complete.connect(self._on_test_complete)

        self._update_button_states()

    def _update_button_states(self, *_args: object) -> None:
        if not hasattr(self, "_run_button"):
            return
        is_running = self._worker is not None and self._worker.isRunning()
        has_device = self._device_selector.selected_device() is not None
        self._run_button.setEnabled(has_device and not is_running)
        self._cancel_button.setEnabled(is_running)

    def _on_devices_changed(self, devices: list[Device]) -> None:
        self._device_selector.set_devices(devices)
        self._update_button_states()

    def _build_artifact_panel(self) -> QWidget:
        card = Card("Artifact under test")
        layout = card.body_layout()

        self._artifact_empty_state = EmptyStateWidget(
            title="No APK Selected",
            message="Select an APK from the app bar or upload a new file to run tests.",
            button_text="Upload APK",
            compact=True,
            frameless=True,
        )
        self._artifact_empty_state.upload_requested.connect(self.upload_requested.emit)
        layout.addWidget(self._artifact_empty_state)

        self._artifact_details = QWidget()
        details_layout = QVBoxLayout(self._artifact_details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(10)

        self._apk_name_label = QLabel("No APK selected")
        self._apk_name_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        details_layout.addWidget(self._apk_name_label)

        self._apk_package_label = QLabel("Select an APK from the app bar")
        self._apk_package_label.setProperty("role", "mono")
        details_layout.addWidget(self._apk_package_label)

        self._tags_layout = QHBoxLayout()
        self._tag_version = QLabel("-")
        self._tag_min = QLabel("-")
        self._tag_target = QLabel("-")
        for tag in (self._tag_version, self._tag_min, self._tag_target):
            tag.setStyleSheet(
                "border: 1px solid #35373e; color: #8b8e94; border-radius: 3px; "
                "padding: 2px 8px; font-size: 11px;"
            )
            self._tags_layout.addWidget(tag)
        self._tags_layout.addStretch(1)
        details_layout.addLayout(self._tags_layout)

        self._artifact_note = QLabel("Select an APK from the app bar to begin.")
        self._artifact_note.setWordWrap(True)
        self._artifact_note.setProperty("role", "muted")
        details_layout.addWidget(self._artifact_note)
        details_layout.addStretch(1)

        layout.addWidget(self._artifact_details)

        # Show empty state by default when no APK is loaded
        self._artifact_details.hide()
        self._artifact_empty_state.show()

        layout.addStretch(1)

        return card

    def _build_sequence_panel(self) -> QWidget:
        card = Card("Run sequence")
        layout = card.body_layout()

        step_definitions = [
            (
                "validate",
                "Validate",
                "androguard · in-process",
                self._profile.validate_manifest,
            ),
            ("install", "Install", "adb -s $S install -r -t app.apk", self._profile.install),
            (
                "launch",
                "Launch",
                "adb -s $S shell monkey -p $PKG -c ...LAUNCHER 1",
                self._profile.launch,
            ),
            (
                "observe",
                "Observe",
                "adb -s $S logcat --pid=$PID -v threadtime",
                self._profile.observe_logcat,
            ),
            (
                "screenshot",
                "Screenshot",
                "adb -s $S exec-out screencap -p",
                self._profile.screenshot,
            ),
            (
                "permissions",
                "Permissions",
                "adb -s $S shell dumpsys package $PKG",
                self._profile.check_permissions,
            ),
            (
                "network",
                "Static hosts",
                "string extraction · deferred to Phase 4",
                self._profile.extract_network_hosts,
            ),
            ("uninstall", "Clean up", "adb -s $S uninstall $PKG", self._profile.uninstall),
        ]

        for step_key, title, command, enabled in step_definitions:
            if not enabled:
                continue
            widget = StepRowWidget(step_key, title, command)
            self._step_widgets[step_key] = widget
            layout.addWidget(widget)

        layout.addStretch(1)
        return card

    def _build_verdict_panel(self) -> QWidget:
        card = Card("Verdict")
        layout = card.body_layout()

        self._verdict_label = QLabel("PENDING")
        self._verdict_label.setStyleSheet("color: #5c5f66; font-size: 22px; font-weight: 800;")
        layout.addWidget(self._verdict_label)

        self._verdict_detail = QLabel("Run a test to see the PASS/FAIL verdict and reason.")
        self._verdict_detail.setWordWrap(True)
        self._verdict_detail.setProperty("role", "muted")
        layout.addWidget(self._verdict_detail)

        captured_label = QLabel("CAPTURED")
        captured_label.setStyleSheet(
            "color: #5c5f66; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; margin-top: 8px;"
        )
        layout.addWidget(captured_label)

        self._capture_box = QFrame()
        self._capture_box.setProperty("role", "card")
        self._capture_box.setFixedHeight(120)
        capture_layout = QVBoxLayout(self._capture_box)
        capture_layout.setContentsMargins(4, 4, 4, 4)

        self._screenshot_label = QLabel("Screenshot pending")
        self._screenshot_label.setProperty("role", "muted")
        self._screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        capture_layout.addWidget(self._screenshot_label)
        layout.addWidget(self._capture_box)

        self._log_excerpt_view = QPlainTextEdit()
        self._log_excerpt_view.setReadOnly(True)
        self._log_excerpt_view.setFixedHeight(90)
        self._log_excerpt_view.setProperty("role", "mono")
        self._log_excerpt_view.setStyleSheet(
            "font-family: 'Cascadia Mono'; font-size: 11px; background: #151618;"
        )
        self._log_excerpt_view.hide()
        layout.addWidget(self._log_excerpt_view)

        self._open_report = QPushButton("▤  Open report")
        self._open_report.setProperty("role", "link")
        self._open_report.clicked.connect(self._on_open_report)
        self._open_report.setEnabled(False)
        layout.addWidget(self._open_report)

        layout.addStretch(1)
        return card

    def set_apk(self, path: Path | None) -> None:
        self._on_apk_selected(path)

    def _on_apk_selected(self, path: Path | None) -> None:
        if path is None:
            self._apk_path = None
            self._apk_info = None
            self._apk_name_label.setText("No APK selected")
            self._apk_package_label.setText("Select an APK from the app bar")
            self._tag_version.setText("-")
            self._tag_min.setText("-")
            self._tag_target.setText("-")
            self._artifact_note.setText("Select an APK from the app bar to begin.")
            self._artifact_note.setStyleSheet("color: #8b8e94;")
            self._artifact_details.hide()
            self._artifact_empty_state.show()
            return

        self._apk_path = path
        try:
            info = self._ctx.apk_service.inspect(path)
            self._apk_info = info
            self._apk_name_label.setText(path.name)
            self._apk_package_label.setText(info.package_name)
            v_name = info.version_name or str(info.version_code or "1.0")
            v_code = f"({info.version_code})" if info.version_code else ""
            self._tag_version.setText(f"{v_name} {v_code}".strip())
            self._tag_min.setText(f"min {info.min_sdk or '?'}")
            self._tag_target.setText(f"target {info.target_sdk or '?'}")
            self._artifact_note.setText("Ready to run automated test cycle.")
            self._artifact_note.setStyleSheet("color: #8b8e94;")
            self._artifact_empty_state.hide()
            self._artifact_details.show()
        except Exception as exc:
            self._apk_name_label.setText(path.name)
            self._apk_package_label.setText("Parse error")
            self._artifact_note.setText(f"Failed to inspect APK: {exc}")
            self._artifact_note.setStyleSheet("color: #e0574a;")
            self._artifact_empty_state.hide()
            self._artifact_details.show()

    def _on_run_test(self) -> None:
        if not self._apk_path or not self._apk_path.is_file():
            self._artifact_note.setText("Please select an APK from the app bar first.")
            self._artifact_note.setStyleSheet("color: #e0574a;")
            QMessageBox.warning(
                self,
                "No APK Selected",
                "No APK file selected.\n\n"
                "Please select an APK from the app bar or upload an APK file before running tests.",
            )
            return

        device = self._device_selector.selected_device()
        if not device:
            self._update_button_states()
            self._verdict_detail.setText(
                "No emulator connected. Please connect an Android device or start an emulator."
            )
            self._verdict_detail.setStyleSheet("color: #e0574a;")
            QMessageBox.warning(
                self,
                "No Emulator Connected",
                "No Android device or emulator is currently connected.\n\n"
                "Please connect an Android device via USB/Wi-Fi or start an emulator to run tests.",
            )
            return

        for widget in self._step_widgets.values():
            widget.reset()

        self._verdict_label.setText("RUNNING")
        self._verdict_label.setStyleSheet("color: #3b82f6; font-size: 22px; font-weight: 800;")
        self._verdict_detail.setText("Running automated test cycle...")
        self._verdict_detail.setStyleSheet("color: #8b8e94;")
        self._screenshot_label.clear()
        self._screenshot_label.setText("Screenshot pending...")
        self._log_excerpt_view.clear()
        self._log_excerpt_view.hide()
        self._run_button.setEnabled(False)
        self._cancel_button.setEnabled(True)
        self._open_report.setEnabled(False)

        output_dir = self._ctx.settings.data_dir / "screenshots"
        output_dir.mkdir(parents=True, exist_ok=True)

        self._worker = TestWorker(
            apk_service=self._ctx.apk_service,
            apk_path=self._apk_path,
            device_serial=device.serial,
            profile=self._profile,
            output_dir=output_dir,
            parent=self,
        )
        self._worker.start()

    def _on_cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._update_button_states()
            self._verdict_label.setText("CANCELLED")
            self._verdict_label.setStyleSheet("color: #e0574a; font-size: 22px; font-weight: 800;")

    def _on_step_started(self, step_name: str) -> None:
        norm = step_name.lower().replace(" ", "_")
        widget = self._step_widgets.get(norm)
        if widget:
            widget.set_running()

    def _on_step_finished(self, step_name: str, passed: bool) -> None:
        norm = step_name.lower().replace(" ", "_")
        widget = self._step_widgets.get(norm)
        if widget:
            widget.set_finished(passed)

    def _on_test_complete(self, run: object) -> None:
        if not isinstance(run, TestRun):
            return

        self._last_run = run
        self._update_button_states()
        self._open_report.setEnabled(True)

        for step in run.steps:
            norm = step.name.lower().replace(" ", "_")
            widget = self._step_widgets.get(norm)
            if widget:
                widget.set_finished(step.passed, step.duration_ms, step.detail)

        verdict_str = str(run.verdict)
        verdict_color = {
            Verdict.PASS: "#27ae60",
            Verdict.PASS_WITH_WARNINGS: "#f1c40f",
            Verdict.FAIL: "#e0574a",
        }.get(run.verdict, "#e0574a")

        self._verdict_label.setText(verdict_str)
        self._verdict_label.setStyleSheet(
            f"color: {verdict_color}; font-size: 22px; font-weight: 800;"
        )

        failed_step = next((s for s in run.steps if not s.passed), None)
        if failed_step:
            detail_text = (
                f"Failed on step '{failed_step.name}': {failed_step.detail or 'Unknown error'}"
            )
        else:
            detail_text = f"Completed all steps in {run.duration_ms} ms."

        self._verdict_detail.setText(detail_text)
        self._verdict_detail.setStyleSheet("color: #eef0f2;")

        if run.screenshot_path and run.screenshot_path.is_file():
            pix = QPixmap(str(run.screenshot_path))
            if not pix.isNull():
                scaled = pix.scaled(
                    self._capture_box.width() - 8,
                    self._capture_box.height() - 8,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._screenshot_label.setPixmap(scaled)
            else:
                self._screenshot_label.setText("Invalid screenshot file")
        else:
            self._screenshot_label.setText("No screenshot captured")

        if run.log_excerpt:
            self._log_excerpt_view.setPlainText(run.log_excerpt)
            self._log_excerpt_view.show()
        else:
            self._log_excerpt_view.hide()

    def _on_open_report(self) -> None:
        if not self._last_run:
            return
        try:
            from droiddesk.services.report_service import ReportService

            reporter = ReportService()
            html_content = reporter.render_test_report(self._last_run, "html")

            report_dir = self._ctx.settings.data_dir / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_file = report_dir / f"test_report_{int(time.time())}.html"
            report_file.write_text(str(html_content), encoding="utf-8")

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(report_file)))
        except Exception as exc:
            self._verdict_detail.setText(f"Error generating report: {exc}")
