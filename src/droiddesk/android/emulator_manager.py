"""Emulator Lifecycle Manager.

Handles launching, tracking, boot detection, stopping, restarting, and lock management.
"""

from __future__ import annotations

import contextlib
import ctypes
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal

from droiddesk.android.command_runner import CommandRunner
from droiddesk.android.models import EmulatorState
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.tools import ToolLocator

if TYPE_CHECKING:
    from droiddesk.android.avd_manager import AvdManager


def is_pid_alive(pid: int) -> bool:
    """Check whether a process ID is currently alive on the host system."""
    if pid <= 0:
        return False
    try:
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def clean_stale_locks(avd_path: Path) -> list[str]:
    """Remove stale, unheld .lock files or directories from an AVD directory.

    If an emulator is genuinely running and locking the file, Windows will raise
    PermissionError so active emulator locks are preserved.
    """
    removed: list[str] = []
    if not avd_path.exists() or not avd_path.is_dir():
        return removed

    for lock_path in avd_path.glob("*.lock"):
        try:
            if lock_path.is_file():
                lock_path.unlink()
                removed.append(lock_path.name)
            elif lock_path.is_dir():
                shutil.rmtree(lock_path)
                removed.append(lock_path.name)
        except (PermissionError, OSError) as exc:
            logger.debug(
                f"Lock file '{lock_path.name}' is currently held by a running process: {exc}"
            )
    return removed


def resolve_running_avd_name(
    adb_path: Path | str, runner: CommandRunner, serial: str
) -> str | None:
    """Resolve AVD name for an emulator serial using multiple reliable strategies."""
    # Strategy 1: Check temporary avd running directory (%TEMP%\avd\running\pid_<PID>.ini)
    try:
        temp_dir = Path(tempfile.gettempdir()) / "avd" / "running"
        if temp_dir.exists():
            for ini_path in temp_dir.glob("pid_*.ini"):
                try:
                    content = ini_path.read_text(encoding="utf-8", errors="replace")
                    m_port = re.search(r"^port\.serial\s*=\s*(\d+)", content, re.MULTILINE)
                    m_avd = re.search(r"^avd\.id\s*=\s*(.+)", content, re.MULTILINE)
                    if (
                        m_port
                        and m_avd
                        and f"emulator-{m_port.group(1).strip()}" == serial
                    ):
                        return m_avd.group(1).strip()
                except Exception:
                    pass
    except Exception:
        pass

    # Strategy 2: adb shell getprop ro.boot.qemu.avd_name (instant & reliable)
    try:
        res = runner.run(
            adb_path,
            ["-s", serial, "shell", "getprop", "ro.boot.qemu.avd_name"],
            timeout=3.0,
        )
        if res.exit_code == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    # Strategy 3: adb emu avd name (fallback)
    try:
        res = runner.run(adb_path, ["-s", serial, "emu", "avd", "name"], timeout=3.0)
        if res.exit_code == 0:
            lines = [
                line.strip()
                for line in res.stdout.splitlines()
                if line.strip() and "OK" not in line
            ]
            if lines:
                return lines[0]
    except Exception:
        pass

    return None


def parse_emulator_error(raw_output: str, exit_code: int) -> tuple[str, str]:
    """Parse emulator output and return (friendly_title, detailed_cause)."""
    text = raw_output or ""

    if "Running multiple emulators with the same AVD" in text:
        title = "Another emulator instance is already running with this AVD."
        details = (
            "The Android Emulator detected that this virtual device is currently in use.\n\n"
            "Possible causes:\n"
            "• An emulator for this AVD is already running in the background or minimized.\n"
            "• A previous emulator process terminated unexpectedly and left lock files "
            "in the AVD directory.\n\n"
            "Solution: If no emulator is open, click 'Release Locks' to clear stale session locks."
        )
        return title, details

    if "hasSufficientDiskSpace" in text and "Failed" in text:
        title = "Insufficient disk space to run emulator."
        details = (
            "The host machine does not have enough free disk space to run this virtual device.\n"
            "Free up disk space on your drive and try again."
        )
        return title, details

    if (
        "Broken AVD system path" in text
        or "is not a valid directory" in text
        or "Missing system image" in text
        or "Unknown AVD name" in text
        or "PANIC: Cannot find AVD system path" in text
    ):
        title = "Missing or invalid Android system image."
        details = (
            "The Android Emulator cannot start because the required system image "
            "is missing or invalid.\n\n"
            "Solution: Install the required system image via Android Studio or SDK Manager, "
            "or recreate the virtual device with an installed system image."
        )
        return title, details

    # Extract non-INFO lines for cleaner error detail
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and not line.strip().startswith("INFO")
        and "Ignore IPv6" not in line
    ]
    err_snippet = "\n".join(lines[-8:]) if lines else f"Process exited with code {exit_code}"
    return "Emulator failed to launch.", err_snippet


class EmulatorBootWorker(QThread):
    """Worker thread that launches emulator, polls ADB, and waits for boot completion."""

    state_changed = Signal(str, str, str)  # (avd_name, state_str, detail_msg)
    finished_success = Signal(str, str)  # (avd_name, serial)
    failed = Signal(str, str, str)  # (avd_name, friendly_title, detailed_cause)

    def __init__(
        self,
        avd_name: str,
        emulator_path: Path,
        adb_client: AdbClient,
        runner: CommandRunner,
        avd_path: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._avd_name = avd_name
        self._emulator_path = emulator_path
        self._adb = adb_client
        self._runner = runner
        self._avd_path = avd_path
        self._proc: subprocess.Popen[Any] | None = None
        self._log_file_path: Path | None = None

    def run(self) -> None:
        try:
            self.state_changed.emit(
                self._avd_name, EmulatorState.STARTING.value, "Launching emulator process..."
            )
            logger.info(
                f"Launching emulator for AVD '{self._avd_name}' via {self._emulator_path}..."
            )

            # 1. Clean up stale unheld locks from prior crashes before spawning
            if self._avd_path:
                cleaned = clean_stale_locks(self._avd_path)
                if cleaned:
                    logger.info(
                        f"Cleaned {len(cleaned)} stale lock file(s) for "
                        f"'{self._avd_name}': {cleaned}"
                    )

            # 2. Launch emulator process with output redirected to log file
            log_dir = Path(tempfile.gettempdir()) / "droiddesk" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            self._log_file_path = log_dir / f"emulator_{self._avd_name}.log"

            with open(self._log_file_path, "w", encoding="utf-8", errors="replace") as log_file:
                self._proc = self._runner.spawn(
                    self._emulator_path,
                    ["-avd", self._avd_name, "-netdelay", "none", "-netspeed", "full"],
                    show_window=True,
                    log_file=log_file,
                )

                # Wait for emulator to register with ADB
                serial: str | None = None
                start_wait = time.perf_counter()
                max_adb_wait_s = 60.0

                while time.perf_counter() - start_wait < max_adb_wait_s:
                    if self.isInterruptionRequested():
                        return
                    # Check if process crashed immediately
                    if self._proc.poll() is not None:
                        full_log = ""
                        with contextlib.suppress(Exception):
                            full_log = self._log_file_path.read_text(
                                encoding="utf-8", errors="replace"
                            )
                        title, details = parse_emulator_error(full_log, self._proc.returncode)
                        logger.error(f"Emulator process died immediately: {title}")
                        self.state_changed.emit(self._avd_name, EmulatorState.ERROR.value, title)
                        self.failed.emit(self._avd_name, title, details)
                        return

                    # Check ADB devices
                    try:
                        devices = self._adb.list_devices()
                        for dev in devices:
                            if dev.serial.startswith("emulator-"):
                                # Check if this emulator belongs to our AVD
                                avd_resp = self._get_emulator_avd_name(dev.serial)
                                if (
                                    avd_resp
                                    and avd_resp.strip().lower() == self._avd_name.strip().lower()
                                ):
                                    serial = dev.serial
                                    break
                                elif not avd_resp:
                                    # Fallback if single running emulator
                                    emu_count = sum(
                                        1 for d in devices if d.serial.startswith("emulator-")
                                    )
                                    if emu_count == 1:
                                        serial = dev.serial
                                        break
                    except Exception:
                        pass

                    if serial:
                        break
                    time.sleep(1.5)

                if not serial:
                    err_msg = (
                        f"Timed out after {max_adb_wait_s}s waiting for emulator to connect to ADB."
                    )
                    self.state_changed.emit(
                        self._avd_name, EmulatorState.ERROR.value, "ADB connection timeout."
                    )
                    self.failed.emit(self._avd_name, "ADB connection timeout", err_msg)
                    return

                # Wait for Android Boot Completion (sys.boot_completed == 1)
                self.state_changed.emit(
                    self._avd_name,
                    EmulatorState.BOOTING.value,
                    f"Emulator connected ({serial}). Waiting for Android to boot...",
                )
                logger.info(
                    f"Emulator '{self._avd_name}' connected ({serial}). "
                    "Polling sys.boot_completed..."
                )

                boot_start = time.perf_counter()
                max_boot_wait_s = 180.0
                is_booted = False

                while time.perf_counter() - boot_start < max_boot_wait_s:
                    if self.isInterruptionRequested():
                        return
                    if self._proc.poll() is not None:
                        full_log = ""
                        with contextlib.suppress(Exception):
                            full_log = self._log_file_path.read_text(
                                encoding="utf-8", errors="replace"
                            )
                        title, details = parse_emulator_error(full_log, self._proc.returncode)
                        self.state_changed.emit(self._avd_name, EmulatorState.ERROR.value, title)
                        self.failed.emit(self._avd_name, title, details)
                        return

                    try:
                        boot_prop = self._adb.getprop(serial, "sys.boot_completed").strip()
                        anim_prop = self._adb.getprop(serial, "init.svc.bootanim").strip()
                        if boot_prop == "1":
                            is_booted = True
                            break
                        elif anim_prop:
                            self.state_changed.emit(
                                self._avd_name,
                                EmulatorState.BOOTING.value,
                                f"Booting Android ({anim_prop})...",
                            )
                    except Exception:
                        pass

                    time.sleep(2.0)

            if not is_booted:
                err_msg = f"Timed out waiting for Android boot completion on {serial}."
                self.state_changed.emit(
                    self._avd_name, EmulatorState.ERROR.value, "Boot completion timeout."
                )
                self.failed.emit(self._avd_name, "Boot completion timeout", err_msg)
                return

            logger.info(f"Emulator '{self._avd_name}' ({serial}) fully booted and RUNNING!")
            self.state_changed.emit(
                self._avd_name, EmulatorState.RUNNING.value, "Android is fully booted and ready."
            )
            self.finished_success.emit(self._avd_name, serial)

        except Exception as exc:
            logger.exception(f"Unexpected error in EmulatorBootWorker for {self._avd_name}: {exc}")
            self.state_changed.emit(self._avd_name, EmulatorState.ERROR.value, "Launch error.")
            self.failed.emit(self._avd_name, "Emulator launch failed", str(exc))

    def _get_emulator_avd_name(self, serial: str) -> str | None:
        return resolve_running_avd_name(self._adb.adb_path, self._runner, serial)


class EmulatorStopWorker(QThread):
    """Worker thread that gracefully stops an emulator via ADB or process termination."""

    finished = Signal(str)  # avd_name

    def __init__(
        self,
        avd_name: str,
        serial: str | None,
        proc: subprocess.Popen[str] | None,
        adb_client: AdbClient,
        runner: CommandRunner,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._avd_name = avd_name
        self._serial = serial
        self._proc = proc
        self._adb = adb_client
        self._runner = runner

    def run(self) -> None:
        logger.info(f"Stopping emulator '{self._avd_name}' (serial={self._serial})...")

        # 1. Try clean shutdown via adb emu kill
        if self._serial:
            try:
                self._runner.run(
                    self._adb.adb_path, ["-s", self._serial, "emu", "kill"], timeout=10.0
                )
            except Exception as exc:
                logger.warning(f"Failed to issue 'emu kill' on {self._serial}: {exc}")

        # 2. Wait for process or terminate
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5.0)
            except Exception:
                with contextlib.suppress(Exception):
                    self._proc.kill()

        # 3. Wait until serial disappears from adb
        if self._serial:
            for _ in range(10):
                try:
                    devs = self._adb.list_devices()
                    if not any(d.serial == self._serial for d in devs):
                        break
                except Exception:
                    break
                time.sleep(1.0)

        logger.info(f"Emulator '{self._avd_name}' has stopped.")
        self.finished.emit(self._avd_name)


class EmulatorManager(QObject):
    """Manages the full lifecycle and state of Android Virtual Devices."""

    state_changed = Signal(str, str, str)  # (avd_name, state_string, detail)
    emulator_started = Signal(str, str)  # (avd_name, serial)
    emulator_stopped = Signal(str)  # avd_name
    emulator_start_failed = Signal(str, str, str)  # (avd_name, title, details)

    def __init__(
        self,
        tool_locator: ToolLocator,
        adb_client: AdbClient,
        runner: CommandRunner | None = None,
        avd_manager: AvdManager | None = None,
    ) -> None:
        super().__init__()
        self._tool_locator = tool_locator
        self._adb = adb_client
        self._runner = runner or CommandRunner(tool_locator)
        self._avd_mgr = avd_manager

        # Track runtime states
        self._states: dict[str, EmulatorState] = {}
        self._active_serials: dict[str, str] = {}  # avd_name -> adb_serial
        self._active_procs: dict[str, subprocess.Popen[str]] = {}  # avd_name -> Popen
        self._workers: dict[str, QThread] = {}

    def get_state(self, avd_name: str) -> EmulatorState:
        return self._states.get(avd_name, EmulatorState.STOPPED)

    def set_state(self, avd_name: str, state: EmulatorState, message: str = "") -> None:
        self._states[avd_name] = state
        self.state_changed.emit(avd_name, state.value, message)

    def get_serial(self, avd_name: str) -> str | None:
        return self._active_serials.get(avd_name)

    def is_running(self, avd_name: str) -> bool:
        return self.get_state(avd_name) == EmulatorState.RUNNING

    def is_busy(self, avd_name: str) -> bool:
        state = self.get_state(avd_name)
        return state in (
            EmulatorState.STARTING,
            EmulatorState.BOOTING,
            EmulatorState.STOPPING,
            EmulatorState.DELETING,
        )

    def get_avd_path(self, avd_name: str) -> Path | None:
        """Resolve path to AVD directory."""
        if self._avd_mgr:
            p = self._avd_mgr.get_avd_path(avd_name)
            if p:
                return p
        default_p = Path.home() / ".android" / "avd" / f"{avd_name}.avd"
        return default_p if default_p.exists() else None

    def _find_pid_for_avd(self, avd_name: str) -> int | None:
        try:
            temp_dir = Path(tempfile.gettempdir()) / "avd" / "running"
            if temp_dir.exists():
                for ini_path in temp_dir.glob("pid_*.ini"):
                    try:
                        content = ini_path.read_text(encoding="utf-8", errors="replace")
                        m_avd = re.search(r"^avd\.id\s*=\s*(.+)", content, re.MULTILINE)
                        if m_avd and m_avd.group(1).strip() == avd_name:
                            m_pid = re.search(r"pid_(\d+)\.ini", ini_path.name)
                            if m_pid:
                                return int(m_pid.group(1))
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    def _find_serial_for_avd(self, avd_name: str) -> str | None:
        try:
            temp_dir = Path(tempfile.gettempdir()) / "avd" / "running"
            if temp_dir.exists():
                for ini_path in temp_dir.glob("pid_*.ini"):
                    try:
                        content = ini_path.read_text(encoding="utf-8", errors="replace")
                        m_avd = re.search(r"^avd\.id\s*=\s*(.+)", content, re.MULTILINE)
                        m_port = re.search(r"^port\.serial\s*=\s*(\d+)", content, re.MULTILINE)
                        if m_avd and m_port and m_avd.group(1).strip() == avd_name:
                            return f"emulator-{m_port.group(1).strip()}"
                    except Exception:
                        pass
        except Exception:
            pass
        return None

    def sync_with_adb_devices(self) -> None:
        """Query ADB to identify any running emulators and match them with AVD names."""
        try:
            devices = self._adb.list_devices()
        except Exception:
            return

        running_serials: dict[str, str] = {}  # avd_name -> serial
        for dev in devices:
            if dev.serial.startswith("emulator-"):
                avd_name = self.get_avd_name_for_serial(dev.serial)
                if avd_name:
                    running_serials[avd_name] = dev.serial

        # Update our state dictionary
        for avd_name, serial in running_serials.items():
            self._active_serials[avd_name] = serial
            current_state = self.get_state(avd_name)
            # Verify boot completion
            try:
                boot_completed = self._adb.getprop(serial, "sys.boot_completed").strip()
                if boot_completed == "1":
                    if current_state != EmulatorState.RUNNING:
                        self.set_state(avd_name, EmulatorState.RUNNING, "Android is running.")
                elif current_state not in (EmulatorState.STARTING, EmulatorState.BOOTING):
                    self.set_state(avd_name, EmulatorState.BOOTING, "Android is booting...")
            except Exception:
                if current_state != EmulatorState.RUNNING:
                    self.set_state(avd_name, EmulatorState.RUNNING, "Android is running.")

        # For any AVD that was RUNNING or BOOTING but is no longer in running_serials
        for avd_name, state in list(self._states.items()):
            if (
                state in (EmulatorState.RUNNING, EmulatorState.BOOTING)
                and avd_name not in running_serials
            ):
                self._states[avd_name] = EmulatorState.STOPPED
                self._active_serials.pop(avd_name, None)
                self.state_changed.emit(
                    avd_name, EmulatorState.STOPPED.value, "Emulator stopped."
                )

    def get_avd_name_for_serial(self, serial: str) -> str | None:
        """Query running emulator for its AVD name."""
        return resolve_running_avd_name(self._adb.adb_path, self._runner, serial)

    def start_emulator(self, avd_name: str) -> None:
        """Start an AVD in a background thread and wait for boot completion."""
        # 1. Refresh active device associations
        self.sync_with_adb_devices()

        if self.is_busy(avd_name):
            logger.warning(
                f"Emulator '{avd_name}' is currently busy ({self.get_state(avd_name).value})."
            )
            return

        if self.is_running(avd_name):
            logger.info(f"Emulator '{avd_name}' is already running.")
            return

        # 2. Check if an active process is registered in temp dir
        pid = self._find_pid_for_avd(avd_name)
        if pid and is_pid_alive(pid):
            logger.info(f"Found active process PID {pid} for '{avd_name}'. Tracking...")
            self.set_state(avd_name, EmulatorState.RUNNING, "Emulator process is active.")
            return

        try:
            emulator_path = self._tool_locator.resolve("emulator")
        except Exception as exc:
            self.set_state(avd_name, EmulatorState.ERROR, f"Emulator tool not found: {exc}")
            return

        avd_path = self.get_avd_path(avd_name)
        if avd_path:
            clean_stale_locks(avd_path)

        self.set_state(avd_name, EmulatorState.STARTING, "Starting emulator...")

        worker = EmulatorBootWorker(
            avd_name=avd_name,
            emulator_path=emulator_path,
            adb_client=self._adb,
            runner=self._runner,
            avd_path=avd_path,
            parent=self,
        )
        self._workers[avd_name] = worker
        worker.state_changed.connect(self._on_worker_state_changed)
        worker.finished_success.connect(self._on_worker_boot_success)
        worker.failed.connect(self._on_worker_boot_failed)
        worker.start()

    def force_release_locks(self, avd_name: str) -> tuple[bool, str]:
        """Release session locks and terminate stuck background processes for an AVD."""
        logger.info(f"Force-releasing locks for '{avd_name}'...")
        # 1. Kill via ADB if serial known
        serial = self._active_serials.get(avd_name)
        if not serial:
            serial = self._find_serial_for_avd(avd_name)
        if serial:
            with contextlib.suppress(Exception):
                self._runner.run(
                    self._adb.adb_path, ["-s", serial, "emu", "kill"], timeout=5.0
                )

        # 2. Check for active PID in temp dir
        pid = self._find_pid_for_avd(avd_name)
        if pid and is_pid_alive(pid):
            with contextlib.suppress(Exception):
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)

        # 3. Clean up lock files in AVD directory
        avd_path = self.get_avd_path(avd_name)
        removed: list[str] = []
        if avd_path:
            removed = clean_stale_locks(avd_path)

        self.set_state(avd_name, EmulatorState.STOPPED, "Locks released.")
        self._active_serials.pop(avd_name, None)
        self._active_procs.pop(avd_name, None)
        return True, f"Released {len(removed)} lock file(s). Status reset to Stopped."

    def stop_emulator(self, avd_name: str) -> None:
        """Stop a running or booting emulator."""
        state = self.get_state(avd_name)
        if state == EmulatorState.STOPPED:
            return

        # Cancel running boot worker if active
        if avd_name in self._workers:
            w = self._workers[avd_name]
            if w.isRunning():
                w.requestInterruption()

        self.set_state(avd_name, EmulatorState.STOPPING, "Stopping emulator...")
        serial = self._active_serials.get(avd_name) or self._find_serial_for_avd(avd_name)
        proc = self._active_procs.get(avd_name)

        stop_worker = EmulatorStopWorker(
            avd_name=avd_name,
            serial=serial,
            proc=proc,
            adb_client=self._adb,
            runner=self._runner,
            parent=self,
        )
        self._workers[f"stop_{avd_name}"] = stop_worker
        stop_worker.finished.connect(self._on_stop_worker_finished)
        stop_worker.start()

    def restart_emulator(self, avd_name: str) -> None:
        """Stop and restart an emulator cleanly."""
        logger.info(f"Restarting emulator '{avd_name}'...")

        def _after_stop(stopped_name: str) -> None:
            if stopped_name == avd_name:
                self.emulator_stopped.disconnect(_after_stop)
                self.start_emulator(avd_name)

        self.emulator_stopped.connect(_after_stop)
        self.stop_emulator(avd_name)

    def _on_worker_state_changed(self, avd_name: str, state_str: str, detail: str) -> None:
        self._states[avd_name] = EmulatorState(state_str)
        self.state_changed.emit(avd_name, state_str, detail)

    def _on_worker_boot_success(self, avd_name: str, serial: str) -> None:
        self._states[avd_name] = EmulatorState.RUNNING
        self._active_serials[avd_name] = serial
        self.state_changed.emit(avd_name, EmulatorState.RUNNING.value, "Ready")
        self.emulator_started.emit(avd_name, serial)

    def _on_worker_boot_failed(self, avd_name: str, title: str, details: str) -> None:
        self._states[avd_name] = EmulatorState.ERROR
        self.state_changed.emit(avd_name, EmulatorState.ERROR.value, title)
        self.emulator_start_failed.emit(avd_name, title, details)

    def _on_stop_worker_finished(self, avd_name: str) -> None:
        self._states[avd_name] = EmulatorState.STOPPED
        self._active_serials.pop(avd_name, None)
        self._active_procs.pop(avd_name, None)
        self.state_changed.emit(avd_name, EmulatorState.STOPPED.value, "Stopped")
        self.emulator_stopped.emit(avd_name)
