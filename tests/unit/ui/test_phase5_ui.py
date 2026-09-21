from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from droiddesk.context import AppContext
from droiddesk.core.models import GateResult, ReleaseCheck
from droiddesk.core.profiles import Environment
from droiddesk.core.severity import GateVerdict
from droiddesk.services.build_service import BuildService
from droiddesk.services.env_service import EnvService
from droiddesk.services.gate_service import GateService
from droiddesk.ui.dialogs.environment_dialog import EnvironmentSwitchDialog
from droiddesk.ui.dialogs.override_dialog import OverrideDialog
from droiddesk.ui.pages.commands import CommandsPage
from droiddesk.ui.pages.gate import GatePage
from droiddesk.ui.widgets.environment_bar import EnvironmentBar


def _make_mock_context(tmp_path: Path) -> AppContext:
    settings = MagicMock()
    settings.data_dir = tmp_path / "data"
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    tool_locator = MagicMock()
    repository = MagicMock()
    device_service = MagicMock()
    apk_service = MagicMock()
    apk_service.list_apks.return_value = []

    env_service = MagicMock(spec=EnvService)
    env_service.project_root = tmp_path
    env_service.active_environment.return_value = None
    env_service.load_environments.return_value = [
        Environment(
            key="staging",
            label="Staging",
            env_file=".env.staging",
            allow_release_build=False,
        ),
        Environment(
            key="production",
            label="Production",
            env_file=".env.prod",
            allow_release_build=True,
        ),
    ]

    build_service = MagicMock(spec=BuildService)
    gate_service = MagicMock(spec=GateService)

    return AppContext(
        settings=settings,
        tool_locator=tool_locator,
        repository=repository,
        device_service=device_service,
        apk_service=apk_service,
        env_service=env_service,
        build_service=build_service,
        gate_service=gate_service,
    )


def test_override_dialog_validation(qapp: QApplication) -> None:
    dialog = OverrideDialog(["git_clean: Working tree dirty"])
    # Confirm button is initially disabled
    assert dialog._confirm_btn.isEnabled() is False

    # Typing a reason enables it
    dialog._reason_edit.setPlainText("Emergency bugfix for incident #1042")
    assert dialog._confirm_btn.isEnabled() is True
    assert dialog.reason() == "Emergency bugfix for incident #1042"


def test_environment_bar_interaction(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    bar = EnvironmentBar(apk_service=ctx.apk_service, settings=ctx.settings)

    requested = []
    bar.switch_requested.connect(lambda: requested.append(True))

    bar._env_button.click()
    assert len(requested) == 1

    # Setting environment updates badge text and styling
    prod = Environment(
        key="production",
        label="Production",
        env_file=".env.prod",
        allow_release_build=True,
    )
    bar.set_environment(prod)
    assert "PRODUCTION" in bar._env_button.text().upper()


def test_environment_switch_dialog(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    assert ctx.env_service is not None
    dialog = EnvironmentSwitchDialog(ctx.env_service)
    assert len(dialog._env_map) == 2


def test_environment_switch_dialog_dynamic(qapp: QApplication, tmp_path: Path) -> None:
    env_service = EnvService(project_root=tmp_path)
    dialog = EnvironmentSwitchDialog(env_service)
    assert len(dialog._env_map) == 0
    assert dialog._switch_btn.isEnabled() is False

    env = Environment(key="dev", label="Development", env_file=".env.dev")
    env_service.add_or_update_environment(env)
    dialog._populate_environments()

    assert len(dialog._env_map) == 1
    assert dialog._switch_btn.isEnabled() is True


def test_environment_edit_dialog(qapp: QApplication, tmp_path: Path) -> None:
    from droiddesk.ui.dialogs.environment_dialog import EnvironmentEditDialog

    env_service = EnvService(project_root=tmp_path)
    dlg = EnvironmentEditDialog(env_service)
    dlg._key_input.setText("staging")
    dlg._label_input.setText("Staging Test")
    dlg._env_file_combo.setCurrentText(".env.staging")
    dlg._on_save()

    loaded = env_service.load_environments()
    assert len(loaded) == 1
    assert loaded[0].key == "staging"
    assert loaded[0].label == "Staging Test"



def test_commands_page_empty_and_active_apk(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = CommandsPage(ctx)
    assert not page._empty_banner.isHidden()

    dummy_apk = tmp_path / "app-debug.apk"
    dummy_apk.write_bytes(b"dummy")
    page.set_apk(dummy_apk)
    assert page._empty_banner.isHidden()


def test_gate_page_verdict_update(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = GatePage(ctx)
    assert not page._empty_state.isHidden()

    dummy_apk = tmp_path / "app-release.apk"
    dummy_apk.write_bytes(b"dummy")
    page.set_apk(dummy_apk)
    assert page._empty_state.isHidden()

    # Simulate GateResult reception
    res = GateResult(
        checks=[
            ReleaseCheck(category="project_identifier", passed=True, weight=10, blocking=True),
            ReleaseCheck(category="environment", passed=True, weight=20, blocking=True),
            ReleaseCheck(category="git_clean", passed=True, weight=10, blocking=False),
        ],
        score=95,
        verdict=GateVerdict.GO,
    )
    page._on_gate_evaluated(res)
    assert page._score_dial._score == 95
    assert page._score_dial._verdict == "GO"
    assert page._blocked_label.text() == "All checks passed"


def test_commands_page_presets(qapp: QApplication, tmp_path: Path) -> None:
    ctx = _make_mock_context(tmp_path)
    page = CommandsPage(ctx)

    # Initially preset 0 (Audit APK Keys)
    assert "APK API Keys" in page._preset_combo.currentText()
    assert page._command_input.isReadOnly() is True
    assert page._run_button.text() == "Run Security Audit"

    # Switch to Assemble Debug
    debug_idx = -1
    for i in range(page._preset_combo.count()):
        if "Assemble Debug" in page._preset_combo.itemText(i):
            debug_idx = i
            break
    assert debug_idx >= 0
    page._preset_combo.setCurrentIndex(debug_idx)
    assert "assembleDebug" in page._command_input.text()
    assert page._command_input.isReadOnly() is False
    assert page._run_button.text() == "Run Command"

    # Switch to Assemble Release
    rel_idx = -1
    for i in range(page._preset_combo.count()):
        if "Assemble Release" in page._preset_combo.itemText(i):
            rel_idx = i
            break
    assert rel_idx >= 0
    page._preset_combo.setCurrentIndex(rel_idx)
    assert "assembleRelease" in page._command_input.text()
    assert page._run_button.text() == "Run Release Build"

    # Test real-time search filter
    assert page._preset_combo.count() == 50
    page._search_input.setText("map")
    assert page._preset_combo.count() >= 1
    assert "Map" in page._preset_combo.currentText()

    # Clear filter restores all 50
    page._search_input.setText("")
    assert page._preset_combo.count() == 50


def test_audit_worker_execution(qapp: QApplication, tmp_path: Path) -> None:
    from droiddesk.ui.pages.commands import AuditWorker

    ctx = _make_mock_context(tmp_path)
    # Create test env file
    env_file = tmp_path / ".env.test"
    env_file.write_text("DATABASE_URL=postgres://user:pass@localhost/db\n", encoding="utf-8")

    worker = AuditWorker(ctx=ctx, apk_path=None, mode="project")
    lines: list[str] = []
    worker.output_line.connect(lines.append)

    worker.run()
    assert any("DATABASE_URL" in line for line in lines)
    assert any("AUDIT & PENETRATION TEST SUMMARY" in line for line in lines)
