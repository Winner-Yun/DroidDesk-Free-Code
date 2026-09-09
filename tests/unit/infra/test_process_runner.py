import sys
from pathlib import Path

import pytest

from droiddesk.core.errors import ProcessTimeoutError
from droiddesk.infra.process import ProcessRunner


def test_process_runner_run_bytes_returns_raw_bytes() -> None:
    runner = ProcessRunner()
    # Use python executable to output exact byte sequence
    python_exe = Path(sys.executable)
    code = "import sys; sys.stdout.buffer.write(b'\\x89PNG\\r\\n\\x1a\\n\\x00\\xff')"
    result = runner.run_bytes(python_exe, ["-c", code])
    assert result == b"\x89PNG\r\n\x1a\n\x00\xff"


def test_process_runner_run_bytes_timeout() -> None:
    runner = ProcessRunner()
    python_exe = Path(sys.executable)
    code = "import time; time.sleep(2)"
    with pytest.raises(ProcessTimeoutError):
        runner.run_bytes(python_exe, ["-c", code], timeout=0.1)
