"""ScreenService: Orchestrates device screen mirroring, recording, and remote control via scrcpy."""

from __future__ import annotations

import contextlib
import ctypes
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from droiddesk.config import Settings
from droiddesk.core.errors import ToolNotFoundError
from droiddesk.core.models import ScreenConfig
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.tools import ToolLocator


class ScreenService(QObject):
    """Manages scrcpy process lifecycle, window embedding, and remote device key events."""

    session_started = Signal(str)  # serial
    session_stopped = Signal(str)  # serial
    session_error = Signal(str, str)  # serial, error_message
    window_ready = Signal(str, int)  # serial, hwnd
    recording_started = Signal(str, Path)  # serial, video_path
    recording_stopped = Signal(str, Path)  # serial, video_path
    recording_saved = Signal(str, Path)  # serial, video_path
    recording_error = Signal(str, str)  # serial, error_message
    resolution_ready = Signal(str, int, int)  # serial, width, height

    def __init__(
        self,
        tool_locator: ToolLocator,
        adb_client: AdbClient,
        settings: Settings,
    ) -> None:
        super().__init__()
        self._tool_locator = tool_locator
        self._adb = adb_client
        self._settings = settings

        self._active_serial: str | None = None
        self._process: QProcess | None = None
        self._config: ScreenConfig | None = None
        self._window_title: str | None = None
        self._hwnd: int = 0
        self._recording_path: Path | None = None
        self._current_resolution: tuple[int, int] | None = None

        # Dedicated recording state
        self._recording_process: QProcess | None = None
        self._recording_serial: str | None = None
        self._recording_target_path: Path | None = None
        self._is_recording_stopping: bool = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._check_window_handle)
        self._poll_attempts = 0

    @property
    def adb_client(self) -> AdbClient:
        return self._adb

    def is_available(self) -> bool:
        """Check if scrcpy executable can be found in PATH, Settings, or bundled tools."""
        return self._tool_locator.is_available("scrcpy")

    def get_scrcpy_path(self) -> Path | None:
        """Return the resolved scrcpy executable path if present."""
        try:
            return self._tool_locator.resolve("scrcpy")
        except ToolNotFoundError:
            return None

    def active_serial(self) -> str | None:
        """Return the currently mirrored device serial, or None."""
        if self._process and self._process.state() == QProcess.ProcessState.Running:
            return self._active_serial
        return None

    def is_mirroring(self, serial: str | None = None) -> bool:
        """Return True if an active scrcpy process is running (optionally matching `serial`)."""
        is_running = (
            self._process is not None and self._process.state() == QProcess.ProcessState.Running
        )
        if not is_running:
            return False
        if serial is not None:
            return self._active_serial == serial
        return True

    def start_mirroring(self, serial: str, config: ScreenConfig | None = None) -> bool:
        """Launch scrcpy for the given device serial."""
        scrcpy_path = self.get_scrcpy_path()
        if not scrcpy_path:
            self.session_error.emit(
                serial,
                "scrcpy executable not found. Install scrcpy or configure its path in Settings.",
            )
            return False

        # If already mirroring another device or this device, stop first
        if self.is_mirroring():
            if self._active_serial == serial:
                return True
            self.stop_mirroring()

        cfg = config or ScreenConfig()
        self._config = cfg
        self._active_serial = serial
        self._hwnd = 0
        self._recording_path = None

        # Clean safe title for window detection
        safe_serial = "".join(c if c.isalnum() else "_" for c in serial)
        self._window_title = f"DroidDesk_Screen_{safe_serial}"

        args: list[str] = ["-s", serial, "--window-title", self._window_title]

        if cfg.embedded:
            args.append("--window-borderless")

        if cfg.max_size > 0:
            args.extend(["-m", str(cfg.max_size)])

        if cfg.bit_rate > 0:
            args.extend(["-b", f"{cfg.bit_rate}M"])

        if cfg.max_fps > 0:
            args.extend(["--max-fps", str(cfg.max_fps)])

        if cfg.stay_awake:
            args.append("--stay-awake")

        if cfg.turn_screen_off:
            args.append("--turn-screen-off")

        if not cfg.forward_audio:
            args.append("--no-audio")

        if cfg.show_touches:
            args.append("--show-touches")

        if cfg.always_on_top and not cfg.embedded:
            args.append("--always-on-top")

        if cfg.fullscreen and not cfg.embedded:
            args.append("--fullscreen")

        if cfg.record_file:
            self._recording_path = cfg.record_file
            cfg.record_file.parent.mkdir(parents=True, exist_ok=True)
            args.extend(["--record", str(cfg.record_file)])

        self._process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("ADB", str(self._adb.adb_path))
        server_path = scrcpy_path.parent / "scrcpy-server"
        if server_path.is_file():
            env.insert("SCRCPY_SERVER_PATH", str(server_path))
        self._process.setProcessEnvironment(env)

        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.readyReadStandardOutput.connect(self._on_scrcpy_output)
        self._process.readyReadStandardError.connect(self._on_scrcpy_output)

        self._process.start(str(scrcpy_path), args)
        started = self._process.waitForStarted(3000)
        if not started:
            self.session_error.emit(serial, "Failed to launch scrcpy process.")
            self._active_serial = None
            return False

        self.session_started.emit(serial)

        # Poll for the window HWND to track window handle and support focus/shortcuts
        if sys.platform == "win32":
            self._poll_attempts = 0
            self._poll_timer.start()

        return True

    def focus_window(self) -> bool:
        """Bring the active scrcpy window to the foreground."""
        if sys.platform == "win32" and self._hwnd != 0:
            with contextlib.suppress(Exception):
                ctypes.windll.user32.ShowWindow(self._hwnd, 9)  # SW_RESTORE
                ctypes.windll.user32.SetForegroundWindow(self._hwnd)
                return True
        return False

    def set_always_on_top(self, on_top: bool) -> bool:
        """Dynamically toggle topmost state of the active scrcpy mirror window."""
        if self._config:
            self._config.always_on_top = on_top
        if sys.platform == "win32" and self._hwnd != 0:
            try:
                hwnd_topmost = -1
                hwnd_notopmost = -2
                swp_nomove = 0x0002
                swp_nosize = 0x0001
                swp_noactivate = 0x0010
                flags = swp_nomove | swp_nosize | swp_noactivate
                target = hwnd_topmost if on_top else hwnd_notopmost
                ctypes.windll.user32.SetWindowPos(self._hwnd, target, 0, 0, 0, 0, flags)
                return True
            except Exception:
                return False
        return False

    def stop_mirroring(self, serial: str | None = None) -> None:
        """Terminate the active scrcpy session."""
        if serial is not None and self._active_serial != serial:
            return

        self._poll_timer.stop()
        proc = self._process
        ended_serial = self._active_serial or ""

        self._process = None
        self._active_serial = None
        self._hwnd = 0

        if proc and proc.state() != QProcess.ProcessState.NotRunning:
            with contextlib.suppress(Exception):
                proc.finished.disconnect(self._on_process_finished)
            proc.terminate()
            if not proc.waitForFinished(1000):
                proc.kill()

        if ended_serial:
            self.session_stopped.emit(ended_serial)

    # -------------------------------------------------------------------------
    # Screen Recording (Headless scrcpy recorder)
    # -------------------------------------------------------------------------

    def is_recording(self, serial: str | None = None) -> bool:
        """Return True if an active screen recording is in progress."""
        is_running = (
            self._recording_process is not None
            and self._recording_process.state() == QProcess.ProcessState.Running
        )
        if not is_running:
            return False
        if serial is not None:
            return self._recording_serial == serial
        return True

    def recording_file(self) -> Path | None:
        """Return the target file path of the current or most recent recording."""
        return self._recording_target_path

    def start_recording(
        self,
        serial: str,
        output_path: Path | None = None,
        config: ScreenConfig | None = None,
    ) -> bool:
        """Launch headless scrcpy recording for the given device serial."""
        scrcpy_path = self.get_scrcpy_path()
        if not scrcpy_path:
            self.recording_error.emit(
                serial,
                "scrcpy executable not found. Install scrcpy or configure its path in Settings.",
            )
            return False

        if self.is_recording():
            if self._recording_serial == serial:
                return True
            self.stop_recording()

        target_path = output_path or self.new_recording_path(serial)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        args: list[str] = [
            "-s",
            serial,
            "--no-playback",
            "--record",
            str(target_path),
        ]

        cfg = config or self._config
        if cfg:
            if cfg.max_size > 0:
                args.extend(["-m", str(cfg.max_size)])
            if cfg.bit_rate > 0:
                args.extend(["-b", f"{cfg.bit_rate}M"])
            if cfg.max_fps > 0:
                args.extend(["--max-fps", str(cfg.max_fps)])
            if not cfg.forward_audio:
                args.append("--no-audio")
        else:
            args.append("--no-audio")

        self._recording_process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("ADB", str(self._adb.adb_path))
        server_path = scrcpy_path.parent / "scrcpy-server"
        if server_path.is_file():
            env.insert("SCRCPY_SERVER_PATH", str(server_path))
        self._recording_process.setProcessEnvironment(env)

        self._recording_process.finished.connect(self._on_recording_finished)
        self._recording_process.errorOccurred.connect(self._on_recording_error)

        self._recording_serial = serial
        self._recording_target_path = target_path
        self._is_recording_stopping = False

        self._recording_process.start(str(scrcpy_path), args)
        started = self._recording_process.waitForStarted(3000)
        if not started:
            self.recording_error.emit(serial, "Failed to launch scrcpy recording process.")
            self._recording_process = None
            self._recording_serial = None
            self._recording_target_path = None
            return False

        self.recording_started.emit(serial, target_path)
        return True

    def stop_recording(self, serial: str | None = None) -> None:
        """Terminate the active screen recording process gracefully."""
        if serial is not None and self._recording_serial != serial:
            return
        if not self._recording_process:
            return
        if self._recording_process.state() == QProcess.ProcessState.NotRunning:
            return

        self._is_recording_stopping = True
        self._recording_process.terminate()
        if not self._recording_process.waitForFinished(3500):
            self._recording_process.kill()

    def _on_recording_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        serial = self._recording_serial or ""
        path = self._recording_target_path

        self._recording_process = None
        self._recording_serial = None
        self._recording_target_path = None
        self._is_recording_stopping = False

        if path and path.is_file() and path.stat().st_size > 0:
            self.recording_saved.emit(serial, path)
            self.recording_stopped.emit(serial, path)
        else:
            if serial:
                self.recording_error.emit(
                    serial, "Recording file could not be created or was saved empty."
                )
                self.recording_stopped.emit(serial, path or Path())

    def _on_recording_error(self, error: QProcess.ProcessError) -> None:
        if self._is_recording_stopping:
            return
        serial = self._recording_serial or ""
        if error == QProcess.ProcessError.FailedToStart:
            msg = "Screen recording process failed to start."
        elif error == QProcess.ProcessError.Crashed:
            msg = "Screen recording process crashed unexpectedly."
        else:
            msg = f"Screen recording process error: {error.name}"
        self.recording_error.emit(serial, msg)

    def _check_window_handle(self) -> None:
        """Poll for the created window HWND on Windows."""
        if not self._window_title or not self._active_serial:
            self._poll_timer.stop()
            return

        self._poll_attempts += 1
        if sys.platform == "win32":
            try:
                hwnd = ctypes.windll.user32.FindWindowW(None, self._window_title)
                if hwnd:
                    self._poll_timer.stop()
                    self._hwnd = hwnd
                    self.window_ready.emit(self._active_serial, hwnd)
                    return
            except Exception:
                pass

        if self._poll_attempts > 60:  # 6 seconds timeout
            self._poll_timer.stop()

    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._poll_timer.stop()
        serial = self._active_serial or ""
        video_path = self._recording_path

        self._process = None
        self._active_serial = None
        self._hwnd = 0

        if serial:
            self.session_stopped.emit(serial)
            if video_path and video_path.exists() and video_path.stat().st_size > 0:
                self.recording_saved.emit(serial, video_path)

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        serial = self._active_serial or ""
        if error == QProcess.ProcessError.FailedToStart:
            msg = "scrcpy failed to start."
        elif error == QProcess.ProcessError.Crashed:
            msg = "scrcpy crashed unexpectedly."
        else:
            msg = f"scrcpy process error: {error.name}"
        self.session_error.emit(serial, msg)

    def _on_scrcpy_output(self) -> None:
        if not self._process or not self._active_serial:
            return
        out = bytes(self._process.readAllStandardOutput().data()).decode("utf-8", errors="ignore")
        err = bytes(self._process.readAllStandardError().data()).decode("utf-8", errors="ignore")
        combined = out + "\n" + err
        import re

        m = re.search(r"Texture:\s*(\d+)x(\d+)", combined)
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            if self._current_resolution != (w, h):
                self._current_resolution = (w, h)
                self.resolution_ready.emit(self._active_serial, w, h)

    def get_resolution(self, serial: str) -> tuple[int, int]:
        """Return the device screen resolution as (width, height)."""
        if self._current_resolution:
            return self._current_resolution
        return self._adb.get_screen_size(serial)

    # -------------------------------------------------------------------------
    # Device Quick Control Key Events (Delegated via ADB)
    # -------------------------------------------------------------------------

    def send_back(self, serial: str) -> None:
        """Trigger Android Back button (KEYCODE_BACK = 4)."""
        self._adb.input_keyevent(serial, 4)

    def send_home(self, serial: str) -> None:
        """Trigger Android Home button (KEYCODE_HOME = 3)."""
        self._adb.input_keyevent(serial, 3)

    def send_app_switch(self, serial: str) -> None:
        """Trigger Android App Switch / Recents (KEYCODE_APP_SWITCH = 187)."""
        self._adb.input_keyevent(serial, 187)

    def send_power(self, serial: str) -> None:
        """Trigger Android Power button (KEYCODE_POWER = 26)."""
        self._adb.input_keyevent(serial, 26)

    def send_volume_up(self, serial: str) -> None:
        """Trigger Android Volume Up (KEYCODE_VOLUME_UP = 24)."""
        self._adb.input_keyevent(serial, 24)

    def send_volume_down(self, serial: str) -> None:
        """Trigger Android Volume Down (KEYCODE_VOLUME_DOWN = 25)."""
        self._adb.input_keyevent(serial, 25)

    def send_rotate(self, serial: str) -> None:
        """Toggle device auto-rotation."""
        # Query current auto-rotate state and toggle
        with contextlib.suppress(Exception):
            self._adb.input_keyevent(serial, 286)  # KEYCODE_REFRESH or rotate shortcut

    def default_recording_dir(self) -> Path:
        """Return the default output directory for screen recording videos."""
        folder = Path.home() / "Videos" / "DroidDesk"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def new_recording_path(self, serial: str) -> Path:
        """Generate a timestamped MP4 recording path for the device."""
        safe_serial = "".join(c if c.isalnum() else "_" for c in serial)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.default_recording_dir() / f"recording_{safe_serial}_{timestamp}.mp4"
