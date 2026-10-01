"""Centralized command execution layer for Android SDK CLI tools."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from droiddesk.core.errors import DroidDeskError
from droiddesk.infra.tools import ToolLocator

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass(slots=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    command: list[str]

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def combined_output(self) -> str:
        out = self.stdout.strip()
        err = self.stderr.strip()
        if out and err:
            return f"{out}\n{err}"
        return out or err


class CommandRunnerError(DroidDeskError):
    """Exception raised when an Android CLI command fails."""

    def __init__(
        self,
        message: str,
        command: list[str],
        exit_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class CommandRunner:
    """Centralized, safe command runner for Android SDK tools.

    Runs ADB, Emulator, AVD Manager, and SDK Manager in isolated subprocesses.
    """

    def __init__(self, tool_locator: ToolLocator) -> None:
        self._tool_locator = tool_locator

    def get_env(self) -> dict[str, str]:
        """Return environment with JAVA_HOME, ANDROID_HOME, and PATH properly configured."""
        env = self._tool_locator.execution_env()
        # Set ANDROID_HOME / ANDROID_SDK_ROOT if resolved
        sdk_root = self._tool_locator._settings.android_sdk_path
        if not sdk_root or not sdk_root.is_dir():
            for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
                val = env.get(key)
                if val and Path(val).is_dir():
                    sdk_root = Path(val)
                    break
        if sdk_root and sdk_root.is_dir():
            env["ANDROID_HOME"] = str(sdk_root)
            env["ANDROID_SDK_ROOT"] = str(sdk_root)
        return env

    def run(
        self,
        program: Path | str,
        args: list[str],
        timeout: float = 30.0,
        cwd: Path | None = None,
        input_text: str | None = None,
        check: bool = False,
    ) -> CommandResult:
        """Run an external tool command synchronously with bounded timeout."""
        cmd = [str(program), *args]
        env = self.get_env()
        start_time = time.perf_counter()

        logger.debug(f"CommandRunner executing: {' '.join(cmd)}")
        try:
            completed = subprocess.run(
                cmd,
                input=input_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=cwd,
                env=env,
                creationflags=_CREATE_NO_WINDOW,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.perf_counter() - start_time
            msg = f"Command timed out after {timeout:.1f}s: {' '.join(cmd)}"
            logger.error(msg)
            raise CommandRunnerError(msg, command=cmd, exit_code=-1) from exc
        except FileNotFoundError as exc:
            msg = f"Executable not found: {program}"
            logger.error(msg)
            raise CommandRunnerError(msg, command=cmd, exit_code=-1) from exc
        except PermissionError as exc:
            msg = f"Permission denied executing: {program}"
            logger.error(msg)
            raise CommandRunnerError(msg, command=cmd, exit_code=-1) from exc
        except OSError as exc:
            msg = f"OS error executing {' '.join(cmd)}: {exc}"
            logger.error(msg)
            raise CommandRunnerError(msg, command=cmd, exit_code=-1) from exc

        duration = time.perf_counter() - start_time
        res = CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_s=duration,
            command=cmd,
        )

        if check and res.exit_code != 0:
            err_details = (
                res.stderr.strip() or res.stdout.strip() or f"Exited with code {res.exit_code}"
            )
            raise CommandRunnerError(
                f"Command failed ({res.exit_code}): {err_details}",
                command=cmd,
                exit_code=res.exit_code,
                stdout=res.stdout,
                stderr=res.stderr,
            )

        return res

    def spawn(
        self,
        program: Path | str,
        args: list[str],
        cwd: Path | None = None,
        show_window: bool = True,
        log_file: object | None = None,
    ) -> subprocess.Popen[Any]:
        """Spawn a detached / background process (e.g. Android Emulator GUI)."""
        cmd = [str(program), *args]
        env = self.get_env()
        creationflags = 0 if show_window else _CREATE_NO_WINDOW

        logger.info(f"CommandRunner spawning process: {' '.join(cmd)}")
        if log_file is not None:
            return subprocess.Popen(
                cmd,
                stdout=log_file,  # type: ignore[arg-type]
                stderr=subprocess.STDOUT,
                cwd=cwd,
                env=env,
                creationflags=creationflags,
                shell=False,
            )
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=cwd,
            env=env,
            creationflags=creationflags,
            shell=False,
        )
