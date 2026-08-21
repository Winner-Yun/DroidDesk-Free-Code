"""ProcessRunner (one-shot, blocking-with-timeout calls) and AdbStream (long-lived,
signal-driven streaming via QProcess). See Section 4.2 and Section 8.1.

Windows rules that apply to every subprocess launched here:
  - CREATE_NO_WINDOW, or QProcess's equivalent, or a console window flashes.
  - Never shell=True — paths and project names contain spaces / user text.
  - Decode with errors="replace" — logcat output is not guaranteed valid UTF-8.
  - Every one-shot call has a timeout; an adb command against a dead device hangs
    indefinitely otherwise.
"""

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
    ) -> ProcessResult:
        try:
            completed = subprocess.run(
                [str(program), *args],
                capture_output=True,
                timeout=timeout,
                cwd=cwd,
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


class AdbStream(QObject):
    """Long-lived streaming process (`adb logcat`, ...). QProcess integrates with
    the Qt event loop natively — no thread is created for I/O-bound subprocess work.
    Verbatim from Section 4.2.
    """

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
        raw = bytes(self._proc.readAllStandardOutput())
        self._buffer += raw.decode("utf-8", errors="replace")
        # emit only complete lines; retain any partial trailing line
        *complete, self._buffer = self._buffer.split("\n")
        for line in complete:
            self.line_received.emit(line.rstrip("\r"))
