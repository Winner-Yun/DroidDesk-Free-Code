"""APK Tester page — Section 6.3. Test profile selection, run button, live per-step
status, and test history backed by test_run.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ApkTesterPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("APK Tester — Phase 3"))
        # TODO(Phase 3): wire to ApkService.step_started/step_finished/test_complete.
