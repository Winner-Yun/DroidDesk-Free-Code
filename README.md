# DroidDesk

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![UI Framework](https://img.shields.io/badge/UI-PySide6%20(Qt%206.7%2B)-41CD52.svg)](https://wiki.qt.io/Qt_for_Python)
[![Platform](https://img.shields.io/badge/Platform-Windows%2064--bit-0078D6.svg)](#)
[![License](https://img.shields.io/badge/License-Proprietary-orange.svg)](#)
[![Code Style](https://img.shields.io/badge/Code%20Style-Ruff-black.svg)](https://github.com/astral-sh/ruff)
[![Type Checker](https://img.shields.io/badge/Type%20Checker-mypy%20(strict)-blue.svg)](https://mypy-lang.org/)

**DroidDesk** is a local, high-performance desktop companion for Android developers, QA engineers, and security reviewers on Windows. It unifies physical device control, low-latency screen mirroring, video recording, real-time Logcat inspection, deep APK analysis, automated smoke testing, offline credential scanning, and environment build guards into a single workstation tool.

Designed under a strict **Local-First** philosophy:
- **100% Offline**: Runs entirely on your local workstation without cloud dependencies.
- **Zero Telemetry**: No user accounts, tracking, or network telemetry.
- **Data Privacy**: Your source code, APKs, test logs, and credentials never leave your machine. State is persisted in a local SQLite database.

---

## Key Features

### Device Control & Screen Mirroring
- **Real-Time Discovery**: Automatically detects connected physical devices and emulators with model, ABI architecture, Android version, API level, and battery metrics.
- **Low-Latency Screen Mirroring**: Integrated `scrcpy` engine embedded directly in the application with mouse and keyboard pass-through, scaling presets, and full-screen view.
- **Headless Video Recording**: Record device screens during reproduction runs or test cycles directly to `.mp4` format.
- **Recordings Gallery**: Visual video manager with automated asynchronous thumbnail generation (`QVideoSink` + frame caching), file metadata inspection, and instant playback.
- **Screen Capture**: One-click high-resolution PNG screenshot capture with local history browsing.

### Deep APK Inspection & Security Audit
- **Manifest Parser**: Drag-and-drop any `.apk` to inspect package name, version name/code, and minimum/target SDKs.
- **Component Breakdown**: Comprehensive inventory of Activities, Services, Broadcast Receivers, and Content Providers with exported status.
- **Permissions Risk Auditor**: Exhaustive list of declared permissions with highlighted dangerous and sensitive capabilities.
- **Signature & Certificate Verification**: Validates APK Signature Schemes (v1, v2, v3, and v4) and extracts MD5, SHA-1, and SHA-256 certificate fingerprints.
- **Offline Secret Scanner**: Built-in `gitleaks` engine to detect accidentally committed API keys, tokens, private keys, and high-entropy credentials in APKs and source directories. Supports suppression rules (`.droiddesk/suppressions.toml`).

### Developer Productivity & QA Automation
- **Zero-Freeze Logcat Viewer**: Real-time log streaming with instant text search, regular expression filters, severity level toggles (Verbose, Debug, Info, Warn, Error, Assert), and excerpt export.
- **Automated Smoke Testing**: Repeatable automated cycles (Install -> Launch -> Observe -> Screenshot -> Crash/ANR Logcat Detection -> Auto-Uninstall) with exportable HTML and PDF reports.
- **ADB Command Center**: Instant shortcuts for common ADB operations, shell commands, package management, and system intents.
- **Environment Switcher & Build Guards**: Switch between Dev, Staging, and Production environments with safety build gates to prevent deploying debug or compromised builds.

---

## Architecture & Project Layout

DroidDesk enforces a strict layered architecture:
- **Core Domain Layer** contains pure dataclasses and business logic (no Qt, no I/O).
- **Infrastructure Layer** handles ADB, subprocess execution, APK parsing, and SQLite persistence.
- **Service Layer** coordinates workflows and emits Qt signals.
- **UI Layer** contains PySide6 widgets and pages, strictly decoupled from direct subprocess calls.

```
src/droiddesk/
├── core/             # Pure domain layer: models, entities, value objects (no Qt, no I/O)
│   ├── models/       # Dataclasses & Pydantic models (Device, Apk, TestRun, Secret, etc.)
│   └── ...
├── infra/            # Infrastructure layer: external tools, parsing, DB
│   ├── adb/          # ADB client, device monitoring, logcat reader, scrcpy integration
│   ├── apk/          # APK parser, manifest analyzer, certificate & signature verifier
│   ├── scanner/      # Gitleaks scanner integration, rules, suppressions
│   ├── db/           # SQLAlchemy engine, SQLite schema, repositories
│   └── tools.py      # SDK toolchain locator (adb, aapt2, apksigner, scrcpy, gitleaks)
├── services/         # Orchestration layer: workflows, state management, Qt signals
│   ├── device.py     # Device discovery & polling service
│   ├── screen.py     # Screen mirroring & headless video recording service
│   ├── logcat.py     # Real-time logcat streaming service
│   ├── apk.py        # APK inspection & testing service
│   └── scanner.py    # Security scanning workflow service
├── ui/               # PySide6 UI layer: widgets, views, pages, viewmodels
│   ├── pages/        # Main application pages (dashboard, analyzer, screen, recordings, etc.)
│   ├── widgets/      # Reusable UI components, thumbnail providers, log viewers
│   ├── dialogs/      # Modal dialogs (recordings dialog, settings, confirmations)
│   ├── themes/       # QSS stylesheets and design tokens
│   └── main_window.py# Main application window shell & navigation
├── reports/          # Jinja2 templates, HTML rendering, and WeasyPrint PDF generator
└── resources/        # Application icons, fonts, QSS files, and bundled tool binaries
```

---

## Tech Stack

- **Language & Runtime:** Python 3.12+ (64-bit)
- **GUI Framework:** [PySide6](https://wiki.qt.io/Qt_for_Python) (Qt 6.7+ with QtMultimedia)
- **Binary & APK Analysis:** [Androguard](https://github.com/androguard/androguard), `pyaxmlparser`, `asn1crypto`, `cryptography`
- **Database & Storage:** SQLite via [SQLAlchemy 2.0](https://www.sqlalchemy.org/)
- **Report Generation:** [Jinja2](https://palletsprojects.com/p/jinja/) and [WeasyPrint](https://weasyprint.org/)
- **External CLI Tools:** Official Android SDK CLI (`adb`, `aapt2`, `apksigner`), pre-bundled [`scrcpy`](https://github.com/Genymobile/scrcpy) & [`gitleaks`](https://github.com/gitleaks/gitleaks)

---

## Getting Started

### 1. Prerequisites
- **Operating System:** Windows 10 or Windows 11 (64-bit / x64).
- **Python:** Python 3.12 or newer.
- **Android SDK:** Ensure Android Studio or standalone Android SDK Platform-Tools is installed. DroidDesk automatically locates `adb` and SDK tools via `ANDROID_HOME` or standard install paths.

### 2. Installation (Development Setup)

Clone the repository and install dependencies using `uv` (recommended) or standard `pip`:

#### Using `uv`:
```bash
# Clone the repository
git clone https://github.com/Winner-Yun/DroidDest.git
cd DroidDest

# Sync environment and install dev dependencies
uv sync --extra dev
uv run pre-commit install
```

#### Using `pip` & virtual environment:
```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
pre-commit install
```

### 3. Verify External Toolchain
```bash
adb version
aapt2 version
```
*(Note: `scrcpy` and `gitleaks` are already pre-bundled inside `src/droiddesk/resources/bin/`).*

### 4. Running the Application
```bash
# Direct run
python -m droiddesk

# Or with uv
uv run python -m droiddesk
```

If you encounter an editable install import issue, reinstall in editable mode:
```bash
pip install -e . --no-deps
```

---

## Quality Gates & Testing

DroidDesk enforces strict type hints, style checking, and comprehensive unit tests:

```bash
# Linting & code formatting checks
ruff check .

# Strict static type checking
mypy src --strict

# Run unit tests (skipping hardware device-dependent tests)
pytest

# Run tests with code coverage report
pytest --cov=src/droiddesk --cov-report=term-missing
```

---

## Building & Packaging

### Standalone Executable (PyInstaller)
To package DroidDesk into a standalone executable folder:
```bash
python packaging/pyinstaller_build.py
```
The output executable will be generated in `dist/droiddesk/`.

### Windows Installer (Inno Setup)
An Inno Setup script is provided to compile a production installer (`DroidDesk-Setup.exe`):
1. Install [Inno Setup 6](https://jrsoftware.org/isdl.php).
2. Open `dist/innnosetupfile/droiddesk.iss` or `packaging/installer.iss`.
3. Click **Compile** to generate the standalone installer under `installer/`.

---

## Configuration & Data Storage

DroidDesk keeps all user data strictly local:
- **Configuration File:** `%APPDATA%\DroidDesk\config.toml` (or standard `platformdirs` location).
- **Local Database:** `%LOCALAPPDATA%\DroidDesk\droiddesk.db` (SQLite).
- **Screenshots & Recordings:** `%LOCALAPPDATA%\DroidDesk\recordings\` and `%LOCALAPPDATA%\DroidDesk\screenshots\`.
- **Thumbnail Cache:** `%LOCALAPPDATA%\DroidDesk\recordings\.thumbnails\`.

---

## Positioning & Security Notice

DroidDesk is a local development, QA, and security auditing assistant. It detects common accidental exposures of credentials, configuration oversights, and application crashes. It is not an enterprise antivirus or a guarantee of exploit prevention. It does not replace comprehensive penetration testing or manual code audits.

---

## License

Proprietary — All rights reserved. See [LICENSE.txt](packaging/LICENSE.txt) for details.


