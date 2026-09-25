"""Subprocess execution helpers and asynchronous output streaming."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from droiddesk.core.errors import ProcessTimeoutError

_CREATE_NO_WINDOW = 0x08000000


@dataclass(slots=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str


class ProcessRunner:
    """Blocking, timeout-bounded execution for one-shot commands (`adb install`,
    `apksigner verify`, `gitleaks detect`, ...). Long-lived streams use AdbStream
    instead.
    """

    def run(
        self,
        program: Path,
        args: list[str],
        timeout: float = 30.0,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessResult:
        try:
            completed = subprocess.run(
                [str(program), *args],
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
                creationflags=_CREATE_NO_WINDOW,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProcessTimeoutError(
                f"{program.name} timed out after {timeout}s: {' '.join(args)}"
            ) from exc

        return ProcessResult(
            exit_code=completed.returncode,
            stdout=completed.stdout.decode("utf-8", errors="replace"),
            stderr=completed.stderr.decode("utf-8", errors="replace"),
        )

    def run_bytes(
        self,
        program: Path,
        args: list[str],
        timeout: float = 30.0,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> bytes:
        try:
            completed = subprocess.run(
                [str(program), *args],
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
                creationflags=_CREATE_NO_WINDOW,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProcessTimeoutError(
                f"{program.name} timed out after {timeout}s: {' '.join(args)}"
            ) from exc

        return completed.stdout


class AdbStream(QObject):
    """Long-lived streaming subprocess integrating with Qt event loop."""

    line_received = Signal(str)
    finished = Signal(int)

    def __init__(self, adb_path: Path, args: list[str]) -> None:
        super().__init__()
        self._buffer = ""
        self._proc = QProcess(self)
        self._proc.setProgram(str(adb_path))
        self._proc.setArguments(args)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(lambda code, _status: self.finished.emit(code))

    def start(self) -> None:
        self._proc.start()

    def stop(self) -> None:
        self._proc.terminate()
        if not self._proc.waitForFinished(2000):
            self._proc.kill()

    def _on_output(self) -> None:
        raw = bytes(self._proc.readAllStandardOutput().data())
        self._buffer += raw.decode("utf-8", errors="replace")
        # emit only complete lines; retain any partial trailing line
        *complete, self._buffer = self._buffer.split("\n")
        for line in complete:
            self.line_received.emit(line.rstrip("\r"))
