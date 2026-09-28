"""PyInstaller build script for DroidDesk.

Alternative packaging method that does not require a C compiler.
Usage:
    pip install pyinstaller
    python packaging/pyinstaller_build.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENTRY_POINT = ROOT / "src" / "droiddesk" / "__main__.py"
ICON_PATH = ROOT / "src" / "droiddesk" / "resources" / "icons" / "droiddesk.ico"
RESOURCES_DIR = ROOT / "src" / "droiddesk" / "resources"
TEMPLATES_DIR = ROOT / "src" / "droiddesk" / "reports" / "templates"

SCANNER_DIR = ROOT / "src" / "droiddesk" / "infra" / "scanner"

PYINSTALLER_ARGS = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--onedir",
    "--windowed",
    "--name=droiddesk",
    f"--paths={ROOT / 'src'}",
    f"--icon={ICON_PATH}",
    f"--add-data={RESOURCES_DIR};resources",
    f"--add-data={RESOURCES_DIR};droiddesk/resources",
    f"--add-data={TEMPLATES_DIR};droiddesk/reports/templates",
    f"--add-data={SCANNER_DIR / 'rules.toml'};droiddesk/infra/scanner",
    f"--add-data={SCANNER_DIR / 'android.toml'};droiddesk/infra/scanner",
    "--collect-data=androguard",
    "--collect-submodules=androguard.core",
    "--collect-submodules=androguard.decompiler",
    "--exclude-module=androguard.pentest",
    "--copy-metadata=androguard",
    "--collect-all=pyaxmlparser",
    "--collect-all=PySide6",
    "--exclude-module=PySide6.QtWebEngineCore",
    "--exclude-module=PySide6.QtWebEngineWidgets",
    "--exclude-module=PySide6.QtWebEngineQuick",
    "--exclude-module=PySide6.QtDesigner",
    "--exclude-module=PySide6.Qt3DCore",
    "--exclude-module=PySide6.Qt3DRender",
    "--exclude-module=PySide6.QtQuick3D",
    "--collect-all=jinja2",
    f"--distpath={ROOT / 'dist'}",
    f"--workpath={ROOT / 'build'}",
    str(ENTRY_POINT),
]


def main() -> int:
    if not ICON_PATH.is_file():
        sys.stderr.write(f"Error: Missing application icon at {ICON_PATH}\n")
        return 1

    target_exe = ROOT / "dist" / "droiddesk" / "droiddesk.exe"
    print(f"Building DroidDesk executable via PyInstaller into {ROOT / 'dist' / 'droiddesk'}...")
    result = subprocess.run(PYINSTALLER_ARGS, cwd=ROOT)
    if result.returncode == 0 and target_exe.is_file():
        print(f"\n[SUCCESS] Executable built successfully: {target_exe}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
