# DroidDesk Development Environment Setup Checklist

This document provides a concise onboarding guide for developers and contributors working on DroidDesk, particularly for testing, scanning, report generation, file organization & renaming, and packaging releases (Phases 3-6).

---

## 1. Python Environment

- **Python Version**: Python 3.12+ (64-bit AMD64).
- **Virtual Environment**:
  ```bash
  uv venv --python 3.12
  .venv\Scripts\activate
  uv sync --extra dev
  ```
  Or via pip:
  ```bash
  pip install -e .[dev]
  ```

---

## 2. Core Dependencies & Quality Gates

Ensure pre-commit and static analyzers pass before committing:
```bash
uv run ruff check .
uv run mypy src --strict
uv run pytest
```

---

## 3. External Toolchain & Android SDK

DroidDesk delegates Android and Git operations to CLI tools. Ensure the following are reachable or configured:

| Tool | Purpose | Discovery Priority |
| :--- | :--- | :--- |
| `adb` | Device control, logcat, profiling | Settings -> `ANDROID_HOME/platform-tools` -> `PATH` |
| `aapt2` | APK resource extraction & validation | Settings -> `ANDROID_HOME/build-tools/<ver>` -> `PATH` |
| `apksigner` | APK signature verification (v1-v4) | Settings -> `ANDROID_HOME/build-tools/<ver>` -> `PATH` |
| `apkanalyzer`| APK DEX/resource breakdown | Settings -> `ANDROID_HOME/cmdline-tools/latest/bin` |
| `git` | Branch tracking & dirty working-tree checks | `PATH` |
| `scrcpy` | Screen mirroring & input capture | Settings -> `PATH` |

- **SDK Default Path**: `%LOCALAPPDATA%\Android\Sdk`

---

## 4. Bundled Security Tooling (`gitleaks`)

- **Location**: `src/droiddesk/resources/bin/gitleaks.exe`
- Gitleaks is shipped directly with DroidDesk for secret scanning.
- End users do **not** need to install Gitleaks globally.
- `ToolLocator.resolve("gitleaks")` automatically locates this bundled binary.

---

## 5. Report Generation & PDF Runtime

- **HTML & Jinja2**: Templates reside in `src/droiddesk/reports/templates/`.
- **PDF Rendering**:
  - WeasyPrint is supported where GTK3 runtime libraries (`libgobject-2.0-0`) are installed.
  - On standard Windows machines without GTK3, DroidDesk automatically uses its built-in **PySide6 `QTextDocument + QPdfWriter`** engine, ensuring zero-dependency, failure-free PDF export.
- **Markdown & JSON**: Generated directly from domain models (`GateResult`, `ScanResult`, `TestRun`).

---

## 6. Smart File Organizer & Renamer

- **Folder Scope**: Can scan and process **any folder** selected by the user.
- **File Types**: Inspects **all file extensions** (`.apk`, `.pdf`, `.png`, `.jpg`, `.zip`, `.exe`, `.docx`, `.mp4`, etc.).
- **Smart Renaming**: Generates clean, standardized filename suggestions (removing download junk, copy tags `(1)`, URL encodings `%20`, and messy delimiters). Supports styles including Smart Clean, kebab-case, snake_case, Date Prefix, and Title Case.
- **Accept Rename**: User reviews suggested names in the preview table and accepts renames with one click.
- **Crash-Resilient Undo**: All renames write a pre-execution JSON journal, allowing 1-click restoration of original filenames at any time.

---

## 7. Packaging & Windows Installer

### Nuitka Executable Build
- Requires Nuitka in the virtual environment:
  ```bash
  uv run nuitka --version
  ```
- Requires a 64-bit C compiler (MinGW64 or MSVC). When prompted, Nuitka can automatically download its cached MinGW64 compiler (`--assume-yes-for-downloads`).
- Build command:
  ```bash
  uv run python packaging/nuitka_build.py
  ```
- Application icon must exist at: `src/droiddesk/resources/icons/droiddesk.ico`

### Inno Setup Installer
- Requires Inno Setup 6 (`iscc.exe`).
- Build setup installer:
  ```bash
  iscc packaging/installer.iss
  ```
- Output installer will be written to `dist/installer/DroidDesk-Setup-0.1.0.exe`.
