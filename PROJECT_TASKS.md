# DroidDesk — Build Task List

A step-by-step checklist for turning the scaffold into a working app. Each task
names the exact file to edit, what to put in it, and how to know you're done.
Work top to bottom — later tasks depend on earlier ones. Full background for
any task is in `DroidDesk-Project-Development.pdf` (section numbers noted below).

Tick boxes as you go: `- [ ]` → `- [x]`.

---

## Phase 0 — Get the app launching (do this first)

You already hit part of this. Finish it before writing any new code.

- [ ] Activate the venv and confirm the package installs cleanly:
  ```powershell
  .venv\Scripts\Activate.ps1
  pip install -e . --no-deps
  pip show droiddesk
  ```
- [ ] Launch it: `python -m droiddesk`. You should see a window with a
  sidebar (Dashboard, Devices) and a status bar. If the window is blank,
  something in `ui/main_window.py` broke — check the terminal for a traceback.
- [ ] Close the app, reopen it, confirm it's repeatable.

**Done when:** the window opens every time without errors.

---

## Phase 1 — Foundation and Device Control

Goal: pick a device from the app and see its real properties.

- [ ] **`config.py` — `Settings.load()` / `Settings.save()`**
  Currently `save()` raises `NotImplementedError`. Read/write `config_file`
  as TOML (use `tomllib` to read, hand-write TOML or use `tomli_w` to write).
  This is where the user's chosen adb/gitleaks paths get remembered between runs.

- [ ] **`infra/adb.py` — `AdbClient.list_devices()`**
  Currently raises `NotImplementedError`. Run `adb devices -l` via
  `ProcessRunner`, parse each line (`SERIAL   device product:X model:Y device:Z`),
  then call `self.getprop()` per device for model/version/API level/ABI.
  Handle the `unauthorized` and `offline` states as distinct — don't treat
  them as errors. (Spec §6.1, Appendix A "Device operations".)

- [ ] **`services/device_service.py` — `DeviceService._poll()`**
  Call `self._adb.list_devices()`, compare against `self._devices`, and only
  emit `devices_changed` when the list actually changed (avoid spamming the
  UI every 2 seconds with an identical list).

- [ ] **`ui/pages/devices.py` — wire it up**
  Connect `DeviceService.devices_changed` to populate `self._device_list`.
  Show unauthorized/offline devices with a distinct label and a "Reconnect"
  button that calls `AdbClient.reconnect()`.

- [ ] **`app.py` — construct `DeviceService`**
  Replace the `# TODO(Phase 1)` comment with real construction, and pass it
  into `MainWindow` so the Devices page can use it.

**Done when:** plugging in a phone (or starting an emulator) makes it appear
in the Devices page within ~2 seconds, with correct model/Android
version/API level, and the state updates when you unplug it.

---

## Phase 2 — APK Analysis and Logcat

Goal: drag an APK onto the app and see its manifest info; stream live logcat.

- [ ] **`infra/apk_reader.py` — `ApkReader.inspect_fast()`**
  Use `pyaxmlparser.APK` (fast, manifest-only) — package name, version name/code,
  min/target SDK. Cache the result in `self._cache` keyed by `hash_file(apk_path)`
  (already imported). Never key by file path (spec §8.5 — a rebuilt APK at the
  same path must not return stale cached data).

- [ ] **`infra/apk_reader.py` — `ApkReader.inspect_full()`**
  Use `androguard.core.apk.APK` for permissions, activities/services/receivers/
  providers, and certificate info. This is slow (~10s on a large APK) — only
  call it when a panel that needs it is actually opened, not on every load.

- [ ] **`ui/pages/analyzer.py` — wire the panels**
  Replace the placeholder `QLabel`s in each tab with real widgets bound to
  the `ApkInfo` returned by `ApkService.inspect()`.

- [ ] **`ui/pages/logcat.py` — wire the stream**
  On device selection, call `AdbClient.logcat_stream()`, connect its
  `line_received` signal to `LogcatModel.queue()` (both already built — this
  is just wiring). Add a `QTableView` bound to the model through a
  `QSortFilterProxyModel`, plus the pause button.

- [ ] **`infra/db.py` — add `Repository.save_apk()`**
  Insert/update a row in the `apk` table (schema already exists) so analyzed
  APKs persist across app restarts.

**Done when:** you can open an APK, see its identity/permissions/signature
info, and separately stream live logcat from a connected device without the
UI freezing.

---

## Phase 3 — Automated Testing

Goal: click "Run Test" and get an install → launch → observe → uninstall
cycle with a pass/fail verdict.

- [x] **`services/test_service.py` — `TestStateMachine.run_step()`**
  One branch per step name (`validate`, `install`, `launch`, `observe`,
  `screenshot`, `permissions`, `uninstall`) — see the command table in spec
  §6.3 / Appendix A for the exact `adb` invocations. Return a
  `TestStepResult` per step.

- [x] **`services/apk_service.py` — `ApkService.run_test()`**
  Drive `TestStateMachine` through the steps enabled on the given
  `TestProfile`, emitting `step_started`/`step_finished` as you go, and use
  `CrashDetector.evaluate()` (already written) on the logcat captured during
  Observe. Assemble and return a `TestRun`, then emit `test_complete`.

- [x] **`infra/adb.py` — fix `AdbClient.screenshot()`**
  It currently decodes PNG bytes as text (there's a `# TODO` marking this).
  Capture raw stdout bytes instead of going through the text-decoding
  `ProcessResult` path — you'll likely need a raw-bytes variant on
  `ProcessRunner` for this one call.

- [x] **`reports/renderer.py` — `html_to_pdf()`**
  Wire up WeasyPrint. **Test this early** — its GTK dependency is flagged in
  the spec (§10.1) as the one packaging risk most likely to bite late. If it
  won't install cleanly on Windows, fall back to ReportLab now rather than at
  release.

- [x] **`ui/pages/apk_tester.py` — wire it up**
  Profile picker, Run button, live per-step status list, connected to
  `ApkService`'s three signals.

**Done when:** running the test against a real device installs the APK,
launches it, captures a screenshot and a log excerpt, uninstalls it, and
shows PASS/FAIL with the reason if it failed.

---

## Phase 4 — Security Scanning

Goal: scan a project folder and get classified findings (not just "secret
found" for everything).

- [ ] **`services/scan_service.py` — `_run_gitleaks()` JSON parsing**
  Parse gitleaks' JSON report into `Finding` objects (map its severity to
  DroidDesk's `Severity` enum).

- [ ] **`services/scan_service.py` — `scan_project()` / `scan_apk()`**
  Wire the gitleaks + engine merge (helper `_merge_and_dedup` already
  exists), move execution onto a `QThreadPool` worker so it doesn't block the
  UI, and support cancellation.

- [ ] **Suppression file handling**
  Read/write `.droiddesk/suppressions.toml` (rule ID + file + line-content
  hash + reason). A suppression lapses automatically if the matched line's
  hash changes — this needs a small helper, probably in `scan_service.py` or
  a new `infra/suppressions.py`.

- [ ] **`ui/pages/security.py` — wire it up**
  `QTableView` on `FindingsModel`, grouped/filterable by severity, with a
  "Suppress" action that writes to the suppressions file.

**Done when:** scanning a folder containing a fake AWS key, a fake Maps API
key, and a UUID produces three *differently classified* findings — critical,
"needs review", and nothing (or low-severity) respectively.

---

## Phase 5 — Environment and Build Control

Goal: switching environments is visible everywhere, and a build command can
be blocked by a guard.

- [ ] **`services/env_service.py` — `EnvService.switch_to()`**
  Back up whatever's currently at the destination paths, copy the new
  `env_file`/`firebase` config into place, emit
  `active_environment_changed`.

- [ ] **`ui/main_window.py` — status bar indicator**
  Connect `EnvService.active_environment_changed` to `self._environment_label`,
  colour it via `ui/theme.py`'s `ENVIRONMENT_RISK_COLORS`.

- [ ] **`services/build_service.py` — `evaluate_guards()` / `run()`**
  One evaluator per guard row in spec §6.9's table. Blocking guards stop
  execution; warning guards need an explicit override with a typed reason
  (see `GateService.override()` for the pattern to follow).

- [ ] **`services/gate_service.py` — `GateService.evaluate()`**
  One evaluator per category in the §6.10 table, short-circuiting on the
  first blocking failure, summing weights into a score.

- [ ] **`ui/pages/commands.py` — wire it up**
  Guard checklist, embedded terminal for `output_line`, override dialog.

**Done when:** switching to "production" shows red in the status bar
everywhere, and running a release command while a critical secret finding
exists gets hard-blocked with a clear reason.

---

## Phase 6 — File Organizer and Release

Goal: point the organizer at a messy folder, preview a plan, apply it, undo it.

- [ ] **`services/organizer_service.py` — `plan()` / `apply()` / `undo()`**
  `plan()`: evaluate each file against loaded `OrganizeRule`s (first match
  wins). `apply()`: perform the moves, updating the journal entry-by-entry.
  `undo()`: replay the journal in reverse.

- [ ] **`ui/pages/organizer.py` — wire it up**
  Rule editor (or just load from TOML for now), preview table before Apply,
  duplicate-group view (backed by `find_duplicates`, already written), Undo
  button.

- [ ] **`packaging/nuitka_build.py` — run it**
  `python packaging/nuitka_build.py` and confirm you get a working `.exe` in
  `dist/`. Expect 90–140 MB — that's normal (spec §10.1).

- [ ] **`packaging/installer.iss` — build the installer**
  Needs Inno Setup installed. Fill in the SDK-detection `[Code]` section
  (currently just a comment placeholder).

**Done when:** you can drop a batch of mixed files into a test folder, preview
the plan, apply it, and undo it back to the original state — and the packaged
`.exe` launches on a machine without Python installed.

---

## Notes on working through this

- Each phase is meant to leave you with something you can actually click
  through — don't skip ahead to Phase 4 before Phase 1 works end to end.
- Every `NotImplementedError` in the codebase marks a task above — search
  for `TODO(Phase` to find them all in place, with the section of the spec
  they map to right next to the code.
- If a task references a spec section (e.g. "§6.3"), that's where the exact
  command table or data shape lives in `DroidDesk-Project-Development.pdf`.
