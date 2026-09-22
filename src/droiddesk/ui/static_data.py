"""Static, hard-coded display data for every page, sourced from the approved
mockups (`ui/*.png` at the repo root). Nothing here performs I/O.

Where a screen's data maps cleanly onto an existing domain model
(`core.models`), that model is used directly so the real service wiring
described in `PROJECT_TASKS.md` can drop in later without changing the shape
pages consume. Where a screen needs a display-only field a domain model
doesn't carry (a human title, a tri-state pass/warn/fail status, a "blocking"
pill), a small `*Row`/`*Display` dataclass wraps it instead of adding
display concerns to the domain layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from droiddesk.core.models import ApkInfo, Device, Finding
from droiddesk.core.severity import Severity

# -- Active environment (top bar + status colouring everywhere) ------------


# (tool name, is available on PATH)
TOOL_STATUS: list[tuple[str, bool]] = [
    ("adb", True),
    ("aapt2", True),
    ("apksigner", True),
    ("gitleaks", True),
    ("bundletool", False),
]

STATUS_MESSAGE = "Idle"

# -- Dashboard ---------------------------------------------------------------


@dataclass(slots=True)
class StatCardData:
    value: str
    label: str


DASHBOARD_STATS: list[StatCardData] = [
    StatCardData("1", "Critical findings"),
    StatCardData("2", "Devices connected"),
    StatCardData("72", "Last gate score"),
    StatCardData("4", "Test runs today"),
]


@dataclass(slots=True)
class AttentionItem:
    severity: str  # critical | high | review
    title: str
    location: str


NEEDS_ATTENTION: list[AttentionItem] = [
    AttentionItem("critical", "Service account private key", "config/service-account.json:4"),
    AttentionItem(
        "high", "Background location from a dependency", "merged manifest · com.analytics.sdk"
    ),
    AttentionItem("review", "Maps API key in resources", "res/values/strings.xml:18"),
]


@dataclass(slots=True)
class RecentRunItem:
    status: str  # pass | fail | warn
    title: str
    when: str


RECENT_RUNS: list[RecentRunItem] = [
    RecentRunItem("fail", "Release gate · production", "12 minutes ago"),
    RecentRunItem("pass", "Smoke test · Pixel 7", "38 minutes ago"),
    RecentRunItem("warn", "Smoke test · emulator-5554", "1 hour ago"),
    RecentRunItem("pass", "Secret scan · full tree", "2 hours ago"),
]

# -- Devices -------------------------------------------------------------


@dataclass(slots=True)
class DeviceRow:
    device: Device
    link: str  # USB | Wi-Fi
    dot: str  # ready | active | unauthorized


DEVICES: list[DeviceRow] = [
    DeviceRow(
        Device(
            "39021FDJH00K3M", "device", "Pixel 7", "14", 34, "arm64-v8a", 420, is_test_profile=True
        ),
        "USB",
        "ready",
    ),
    DeviceRow(
        Device("emulator-5554", "device", "sdk_gphone64_x86_64", "13", 33, "x86_64", None),
        "USB",
        "active",
    ),
    DeviceRow(
        Device("R58M40QW1ZK", "unauthorized", "Galaxy S21", None, None, None, None),
        "USB",
        "unauthorized",
    ),
    DeviceRow(
        Device("192.168.1.24:5555", "device", "Pixel 6a", "14", 34, "arm64-v8a", None),
        "Wi-Fi",
        "ready",
    ),
]

SELECTED_DEVICE = DEVICES[0]

TEST_DEVICE_PROFILE_NOTE = (
    "Marking a device as a test device attaches an allowed-environment policy. "
    "The gate and the test runner both refuse to point it at an environment "
    "outside that policy."
)

# -- APK analyzer -------------------------------------------------------

ANALYZER_APK = ApkInfo(
    file_path=Path("app-release.apk"),
    file_hash="9f1c2e7a4b3d5f60",
    package_name="com.example.app",
    version_name="2.4.1",
    version_code=241,
    target_sdk=34,
    min_sdk=24,
    compile_sdk=34,
    size_bytes=int(38.2 * 1024 * 1024),
    permissions=[
        "android.permission.INTERNET",
        "android.permission.ACCESS_NETWORK_STATE",
        "android.permission.CAMERA",
        "android.permission.READ_EXTERNAL_STORAGE",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_BACKGROUND_LOCATION",
        "android.permission.POST_NOTIFICATIONS",
    ],
    activities=[".MainActivity", ".SettingsActivity", ".onboarding.WelcomeActivity"],
    services=[".sync.SyncWorkerService", "com.analytics.sdk.CollectorService"],
    receivers=[".BootReceiver"],
    providers=[".provider.FileProvider"],
    signature_schemes=[1, 2, 3],
    certificate_fingerprint_sha256="3B:9A:0C:71:E4:22:8F:5D:16:C0:AA:4E:9B:37:D2:61",
)

ANALYZER_CERT = {
    "subject": "CN=Example Ltd, O=Example, C=GB",
    "sha-256": ANALYZER_APK.certificate_fingerprint_sha256,
    "valid from": "2021-04-09",
    "valid to": "2046-04-03",
    "algorithm": "SHA256withRSA · 2048 bit",
}

ANALYZER_HIGH_RISK_PERMISSIONS = {
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.CAMERA",
}

ANALYZER_COMPONENT_COUNTS = [
    ("Activities", len(ANALYZER_APK.activities)),
    ("Services", len(ANALYZER_APK.services)),
    ("Receivers", len(ANALYZER_APK.receivers)),
    ("Providers", len(ANALYZER_APK.providers)),
]

ANALYZER_SIZE_BREAKDOWN = [
    ("classes.dex", "14.8 MB"),
    ("resources.arsc", "2.1 MB"),
    ("res/", "6.4 MB"),
    ("lib/arm64-v8a/", "12.9 MB"),
    ("assets/", "1.6 MB"),
    ("META-INF/", "0.4 MB"),
]

ANALYZER_HOSTS = [
    ("api.example.com", "release endpoint"),
    ("staging-api.example.com", "found in a debug-only string — informational"),
    ("maps.googleapis.com", "Maps SDK"),
    ("firebaseinstallations.googleapis.com", "Firebase"),
]

# -- Test runner ----------------------------------------------------------


@dataclass(slots=True)
class TestStepRow:
    name: str
    status: str  # pass | fail | warn
    headline: str
    command: str
    duration_ms: int


TEST_PROFILE_NAME = "Smoke test"

TEST_RUN_STEPS: list[TestStepRow] = [
    TestStepRow("Validate", "pass", "com.example.app 2.4.1", "androguard · in-process", 180),
    TestStepRow("Install", "pass", "Success", "adb -s $S install -r -t app.apk", 4210),
    TestStepRow(
        "Launch", "pass", "pid 4821", "adb -s $S shell monkey -p $PKG -c ...LAUNCHER 1", 940
    ),
    TestStepRow(
        "Observe",
        "fail",
        "FATAL EXCEPTION in sync-worker",
        "adb -s $S logcat --pid=$PID -v threadtime",
        6100,
    ),
    TestStepRow("Screenshot", "pass", "1080x2400 PNG", "adb -s $S exec-out screencap -p", 620),
    TestStepRow("Permissions", "pass", "9 granted", "adb -s $S shell dumpsys package $PKG", 310),
    TestStepRow(
        "Static hosts",
        "warn",
        "staging-api.example.com found",
        "string extraction · informational only",
        240,
    ),
    TestStepRow("Clean up", "pass", "Success", "adb -s $S uninstall $PKG", 1180),
]

TEST_RUN_VERDICT = "FAIL"
TEST_RUN_VERDICT_DETAIL = (
    "Crash detection matches FATAL EXCEPTION, ANR, process death and SIGSEGV "
    "scoped to the target PID. It does not search for the word \u201cerror\u201d, "
    "which appears constantly in healthy logs."
)
TEST_RUN_NOTE = (
    "A bundle is converted with bundletool --mode=universal before testing. "
    "The report says so, because a universal APK is not what a device "
    "receives from Play."
)

# -- Secret scanner --------------------------------------------------------


@dataclass(slots=True)
class FindingDisplay:
    finding: Finding
    title: str
    recommended_action: str


SECURITY_FINDINGS: list[FindingDisplay] = [
    FindingDisplay(
        Finding(
            "service-account-key",
            Severity.CRITICAL,
            Path("config/service-account.json"),
            "h1",
            '"private_key: "-----BEGIN PRIVATE KEY-----…',
            4,
        ),
        "Google Cloud service account private key",
        "Remove this file from the repository and rotate the key in the Cloud console. "
        "Move the credential to a secret manager or an untracked local file.",
    ),
    FindingDisplay(
        Finding(
            "keystore-tracked",
            Severity.CRITICAL,
            Path("app/release.jks"),
            "h2",
            "binary · 2,432 bytes · JKS magic",
            None,
        ),
        "Signing keystore tracked in the repository",
        "Remove the keystore from version control and rotate the signing key if it "
        "has ever been pushed to a remote.",
    ),
    FindingDisplay(
        Finding(
            "env-database-url",
            Severity.HIGH,
            Path(".env.production"),
            "h3",
            "DATABASE_URL=postgres://app:••••••@db.e…",
            7,
        ),
        "Backend database URL in an .env file",
        "Move production connection strings out of tracked .env files and into a "
        "secret manager; rotate the credential.",
    ),
    FindingDisplay(
        Finding(
            "firebase-legacy-secret",
            Severity.HIGH,
            Path("app/src/main/res/values/secrets.xml"),
            "h4",
            '<string name="fb_secret">AAAA••••••••••••…',
            None,
        ),
        "Legacy Firebase database secret",
        "This legacy secret grants full read/write to the Realtime Database. "
        "Migrate to Firebase security rules and revoke the legacy secret.",
    ),
    FindingDisplay(
        Finding(
            "google-maps-key",
            Severity.NEEDS_REVIEW,
            Path("app/src/main/res/values/strings.xml"),
            "h5",
            '<string name="maps_key">AIzaSy•••••••••••••••••••••</string>',
            18,
        ),
        "Google Maps API key in string resources",
        "Restrict this key — do not remove it. A Maps key is designed to ship "
        "inside the APK. In the Cloud console, restrict it to this package name "
        "and your release SHA-1 fingerprint, and cap it to the Maps SDK.",
    ),
    FindingDisplay(
        Finding(
            "high-entropy-string",
            Severity.NEEDS_REVIEW,
            Path("app/src/main/java/com/example/Auth.kt"),
            "h6",
            'String token = "b7f3••••••••••••••••…',
            None,
        ),
        "High-entropy string assigned to a variable",
        "Confirm whether this is a real credential or a generated test fixture "
        "before deciding whether it needs to move out of source.",
    ),
    FindingDisplay(
        Finding(
            "google-services-present",
            Severity.INFORMATIONAL,
            Path("app/google-services.json"),
            "h7",
            "project_id: example-prod · 3 clients",
            None,
        ),
        "google-services.json present",
        "This file is meant to ship with the app and is not a secret by itself. No action needed.",
    ),
]

SECURITY_SUMMARY = [
    (
        "Critical",
        Severity.CRITICAL,
        sum(1 for f in SECURITY_FINDINGS if f.finding.severity == Severity.CRITICAL),
    ),
    (
        "High",
        Severity.HIGH,
        sum(1 for f in SECURITY_FINDINGS if f.finding.severity == Severity.HIGH),
    ),
    (
        "Needs review",
        Severity.NEEDS_REVIEW,
        sum(1 for f in SECURITY_FINDINGS if f.finding.severity == Severity.NEEDS_REVIEW),
    ),
    (
        "Informational",
        Severity.INFORMATIONAL,
        sum(1 for f in SECURITY_FINDINGS if f.finding.severity == Severity.INFORMATIONAL),
    ),
]

SECURITY_SELECTED = SECURITY_FINDINGS[4]  # Google Maps API key — matches the mockup detail panel

# -- File organizer ---------------------------------------------------------

ORGANIZER_PATH = r"C:\Users\dev\Downloads"
ORGANIZER_HASH_PROGRESS_LABEL = "Hashing tier 3 — 412 of 640 candidates"
ORGANIZER_HASH_PROGRESS = (412, 640)


@dataclass(slots=True)
class OrganizerMoveRow:
    file_name: str
    rule: str
    destination: str


ORGANIZER_PLANNED_MOVES: list[OrganizerMoveRow] = [
    OrganizerMoveRow("app-release-2.4.1.apk", "Release APKs", "APK/Release"),
    OrganizerMoveRow("app-debug.apk", "Debug APKs", "APK/Debug"),
    OrganizerMoveRow("Screenshot_20260814.png", "Screenshots", "Images/Screenshots"),
    OrganizerMoveRow("flutter_project_old.zip", "Stale archives", "Archives/Old"),
    OrganizerMoveRow("bundletool-all-1.15.6.jar", "Tooling", "Tools"),
]

ORGANIZER_DUPLICATE_STATS = [
    ("Files examined", "41,208"),
    ("Size groups with collisions", "1,904"),
    ("Full hashes required", "2,431"),
    ("Duplicate sets found", "86"),
    ("Recoverable space", "3.1 GB"),
]

ORGANIZER_UNDO_BATCH_ID = "batch 2026-08-21T09:14:02Z · 128"
ORGANIZER_UNDO_NOTE = (
    "Written before the first move and updated as each completes. If DroidDesk "
    "is killed mid-run, the journal is found on next launch and a rollback is "
    "offered."
)

# -- Build commands ----------------------------------------------------------


@dataclass(slots=True)
class GuardRow:
    name: str
    status: str  # pass | warn | fail
    detail: str
    tag: str | None


BUILD_COMMAND_NAME = "assembleRelease"

BUILD_GUARDS: list[GuardRow] = [
    GuardRow("environment_matches", "pass", "production · required production", "blocking"),
    GuardRow("release_allowed", "pass", "environment permits releases", "blocking"),
    GuardRow("git_clean", "warn", "3 modified files — overridable", None),
    GuardRow("secret_scan_clean", "fail", "1 critical finding", "blocking"),
    GuardRow("no_debug_flags", "pass", "debuggable absent from manifest", "blocking"),
    GuardRow("version_bumped", "pass", "241 > 238", None),
]

BUILD_GUARD_NOTE = (
    "A hard block cannot be dismissed here. It is lifted by fixing the cause, "
    "or recorded as an override on the release gate."
)

BUILD_OUTPUT = """gradlew.bat assembleRelease --stacktrace

> Task :app:preBuild UP-TO-DATE
> Task :app:compileReleaseKotlin
w: file:///src/main/kotlin/Sync.kt:41 variable 'retry' is never used
> Task :app:mergeReleaseResources

Guard failed: secret_scan_clean
  1 critical finding in the project tree.
  config/service-account.json:4 \u2014 service account private key

Build not started."""

# -- Release gate -------------------------------------------------------


@dataclass(slots=True)
class GateCheckRow:
    name: str
    status: str  # pass | warn | fail
    detail: str
    blocking: bool
    weight: int


GATE_SCORE = 72
GATE_VERDICT = "NO-GO"
GATE_BLOCKED_REASON = "Blocked by 1 critical finding"
GATE_SCORE_NOTE = (
    "The score tracks improvement over time. The verdict governs the build. "
    "They are not the same signal."
)

GATE_CHECKS: list[GateCheckRow] = [
    GateCheckRow(
        "Project",
        "pass",
        "Package name matches the expected release identifier \u2014 com.example.app",
        True,
        10,
    ),
    GateCheckRow(
        "Environment",
        "pass",
        "Production active and permitted to build releases — production · api.example.com",
        True,
        20,
    ),
    GateCheckRow(
        "Git",
        "warn",
        "Working tree clean, on a release branch — 3 modified files on release/2.4",
        False,
        10,
    ),
    GateCheckRow(
        "Secrets",
        "fail",
        (
            "No critical findings in the project tree — "
            "1 critical · config/service-account.json"
        ),
        True,
        20,
    ),
    GateCheckRow(
        "APK",
        "pass",
        "Valid, signed with v2 or later, correct target SDK \u2014 v2 + v3 \u00b7 targetSdk 34",
        True,
        15,
    ),
    GateCheckRow(
        "Privacy",
        "pass",
        "No credential files present inside the APK \u2014 assets/, res/raw/ clean",
        True,
        15,
    ),
    GateCheckRow(
        "Permissions",
        "warn",
        "No unreviewed high-risk permissions \u2014 ACCESS_BACKGROUND_LOCATION unreviewed",
        False,
        5,
    ),
    GateCheckRow(
        "Size", "pass", "Under the configured threshold \u2014 38.2 MB of 60 MB", False, 5
    ),
]

GATE_FOOTER_NOTE = (
    "DroidDesk performs automated checks for commonly misplaced configuration "
    "and credential files. It detects accidental exposure, not deliberate "
    "concealment. All findings should be assessed by a person before acting "
    "on them."
)

# -- Reports ------------------------------------------------------------


@dataclass(slots=True)
class ReportEntry:
    name: str
    kind: str
    verdict: str
    when: str


REPORT_HISTORY: list[ReportEntry] = [
    ReportEntry("gate-2.4.1-production", "Release gate", "NO-GO", "12 min ago"),
    ReportEntry("smoke-pixel7-241", "Test run", "PASS", "38 min ago"),
    ReportEntry("scan-full-tree", "Secret scan", "3 findings", "2 hours ago"),
    ReportEntry("gate-2.4.0-production", "Release gate", "GO", "yesterday"),
]

REPORT_EXPORTS = [
    ("Export as HTML", "Interactive review with collapsible findings"),
    ("Export as PDF", "Archival, client delivery, release ticket"),
    ("Export as JSON", "CI reads the verdict and fails the pipeline"),
    ("Export as Markdown", "Pull request description or issue tracker"),
]

REPORT_FOOTER_NOTE = (
    "Every generated report carries the statement of limitations at its "
    "head. It is not optional and cannot be turned off."
)

# -- Logcat -----------------------------------------------------------------

_LOGCAT_TAGS = [
    "SyncEngine",
    "Analytics",
    "Choreographer",
    "WindowManager",
    "ActivityManager",
    "GraphicsEnv",
    "InputMethodManager",
    "OkHttp",
]
_LOGCAT_MESSAGES = [
    "wakelock released",
    "dispatching update",
    "cache hit for key config.v2",
    "layout pass 14ms",
    "surface created 1080x2400",
    "gc freed 2841 objects",
    "binder transaction complete",
]


def build_logcat_lines(count: int = 80) -> list[str]:
    """Threadtime-format lines, parseable by `ui.models.logcat_model.parse_threadtime`."""
    lines = []
    pid = 4821
    base_tid = 4876
    hour, minute, second = 9, 14, 25
    for i in range(count):
        tag = _LOGCAT_TAGS[i % len(_LOGCAT_TAGS)]
        message = _LOGCAT_MESSAGES[i % len(_LOGCAT_MESSAGES)]
        tid = base_tid + i
        timestamp = f"08-21 {hour:02d}:{minute:02d}:{second:02d}.{(i * 37) % 1000:03d}"
        lines.append(f"{timestamp}  {pid}  {tid} D {tag}: {message}")
        second += 1
        if second >= 60:
            second = 0
            minute += 1
    return lines


LOGCAT_LINE_COUNT = 309
LOGCAT_LINES = build_logcat_lines(LOGCAT_LINE_COUNT)
