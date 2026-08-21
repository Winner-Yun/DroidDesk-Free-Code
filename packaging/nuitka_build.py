"""Nuitka build driver. See Section 10.1 for the flags and their rationale —
in particular `--windows-console-mode=disable` (without it a console window
accompanies the app) and `--include-package-data=androguard` (androguard loads
data files at runtime; omitting this fails only in the packaged build).

Usage: uv run python packaging/nuitka_build.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENTRY_POINT = ROOT / "src" / "droiddesk" / "__main__.py"

NUITKA_ARGS = [
    sys.executable,
    "-m",
    "nuitka",
    "--standalone",
    "--enable-plugin=pyside6",
    "--windows-console-mode=disable",
    f"--windows-icon-from-ico={ROOT / 'src/droiddesk/resources/icons/droiddesk.ico'}",
    f"--include-data-dir={ROOT / 'src/droiddesk/resources'}=droiddesk/resources",
    f"--include-data-dir={ROOT / 'src/droiddesk/reports/templates'}=droiddesk/reports/templates",
    "--include-package-data=androguard",
    f"--output-dir={ROOT / 'dist'}",
    str(ENTRY_POINT),
]


def main() -> int:
    # Expect a 90-140 MB distribution directory (PySide6 + androguard); that is
    # normal for this project, per Section 10.1.
    result = subprocess.run(NUITKA_ARGS, cwd=ROOT)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
