"""PyInstaller build script for DroidDesk.

Alternative packaging method that does not require a C compiler.
Usage:
    pip install pyinstaller
    python packaging/pyinstaller_build.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import psutil

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


def _cleanup_locking_processes(dist_dir: Path) -> None:
    """Terminate any background processes (such as adb.exe daemon or previous runs)
    """
    try:
        target_str = str(dist_dir).lower()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                exe = (p.exe() or "").lower()
                cwd = (p.cwd() or "").lower()
                if target_str in exe or target_str in cwd:
                    p.kill()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

        if dist_dir.exists():
            shutil.rmtree(dist_dir, ignore_errors=True)
    except Exception:
        pass


def main() -> int:
    if not ICON_PATH.is_file():
        sys.stderr.write(f"Error: Missing application icon at {ICON_PATH}\n")
        return 1

    dist_droiddesk = ROOT / "dist" / "droiddesk"
    _cleanup_locking_processes(dist_droiddesk)

    target_exe = dist_droiddesk / "droiddesk.exe"
    print(f"Building DroidDesk executable via PyInstaller into {dist_droiddesk}...")
    result = subprocess.run(PYINSTALLER_ARGS, cwd=ROOT)
    if result.returncode == 0 and target_exe.is_file():
        print(f"\n[SUCCESS] Executable built successfully: {target_exe}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
