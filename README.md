# DroidDesk

Local Android development companion for Windows. Consolidates device control, APK
inspection, automated test runs, secret scanning, and a pre-release gate into a single
desktop application. Runs entirely on the developer's machine no account, no network
transmission, state kept in a local SQLite database.

See `DroidDesk-Project-Development.pdf` for the full specification and development plan.

## Stack

Python 3.12+ · PySide6 (Qt 6.7+) · Androguard · SQLite

## Getting started

```bash
uv sync --extra dev
uv run pre-commit install
```

Or with plain pip:

```bash
pip install -r requirements-dev.txt
pre-commit install
```

Then, from either setup:

```bash
# verify the external toolchain is reachable
adb version
aapt2 version
gitleaks version

# quality gates
ruff check .
mypy src --strict
pytest

# run the app

python -m droiddesk

```

(prefix each with `uv run` if you used `uv sync` rather than `pip install`)

If `python -m droiddesk` fails with `No module named droiddesk`, the editable
install's path record is stale (e.g. after moving/renaming the project folder).
Reinstall it:

```bash
pip install -e . --no-deps
```

DroidDesk delegates every Android operation to the official SDK command-line tools
(`adb`, `aapt2`, `apksigner`, `apkanalyzer`, `bundletool`) plus `gitleaks` for secret
scanning. On first run it looks for an Android SDK via `ANDROID_HOME` /
`ANDROID_SDK_ROOT`, the default install location, or `PATH`, and prompts if none is
found. See Section 3 of the spec for the full discovery strategy.

## Project layout

```
src/droiddesk/
├── core/        # domain layer — dataclasses/Pydantic models, no I/O, no Qt
├── infra/       # infrastructure — subprocess, adb, APK parsing, scanner engine, DB
├── services/    # orchestration layer — owns workflows, emits Qt signals
├── ui/          # Qt widgets, pages, table models — no business logic
├── reports/     # Jinja2 templates, HTML/PDF rendering
└── resources/   # icons, fonts, QSS, bundled gitleaks binary
```

Layering rule: nothing under `core/` or `infra/` imports from `ui/`, and nothing under
`ui/` calls `subprocess` directly. See Section 4.1 of the spec.

## Status

Scaffolding only see Section 9 (Development Roadmap) for the six-phase build order,
starting with Phase 1: Foundation and Device Control.

## What this is not

Not a security product or a guarantee of safety. It detects common, accidental
exposure of credentials and misconfiguration not deliberate obfuscation. See
Section 1.4 and Section 12.1 of the spec for the full positioning statement.
