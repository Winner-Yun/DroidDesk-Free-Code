"""Command execution and defensive security audit page."""

from __future__ import annotations

import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.context import AppContext
from droiddesk.core.profiles import CommandProfile, GuardResult
from droiddesk.infra.scanner.gitleaks_mapping import rule_id_to_key_name
from droiddesk.infra.scanner.util import redact_secret
from droiddesk.ui.pages.security import _SEVERITY_RECOMMENDATIONS
from droiddesk.ui.theme import TEXT_MUTED, get_icon
from droiddesk.ui.widgets.card import Card, PageHeader
from droiddesk.ui.widgets.empty_state import EmptyStateWidget


@dataclass(slots=True)
class CommandPreset:
    id: str
    name: str
    command: str
    description: str
    category: str  # "security" | "build" | "adb" | "apk" | "custom"
    is_release: bool = False


_GRADLE = "gradlew.bat" if sys.platform.startswith("win") else "./gradlew"

_CATEGORY_ICONS: dict[str, str] = {
    "security": "shield-check",
    "build": "wrench",
    "adb": "smartphone",
    "apk": "package-search",
    "custom": "terminal",
}

_CATEGORY_COLORS: dict[str, str] = {
    "security": "#38bdf8",
    "build": "#f59e0b",
    "adb": "#27ae60",
    "apk": "#a855f7",
    "custom": "#9ca3af",
}

PRESET_COMMANDS: list[CommandPreset] = [
    # Security & Key Harvesting Defensive Audits
    CommandPreset(
        id="audit_apk_keys",
        name="[Audit] APK API Keys & Secrets",
        command="audit:apk-keys",
        description="Extracts resources.arsc strings and assets to detect extractable API keys.",
        category="security",
    ),
    CommandPreset(
        id="audit_project_secrets",
        name="[Audit] Project & Config Secrets",
        command="audit:project-secrets",
        description="Scans .env, properties, and source code for exposed backend secrets.",
        category="security",
    ),
    CommandPreset(
        id="audit_full_pentest",
        name="[Audit] Full Key Harvesting Pentest",
        command="audit:full-pentest",
        description="Comprehensive defensive test combining APK extraction and repo scanning.",
        category="security",
    ),
    CommandPreset(
        id="audit_maps_keys",
        name="[Audit] Google Maps Key Leak",
        command="audit:maps-keys",
        description="Hunts for Google Maps API keys (AIzaSy...) and checks SHA-1 restriction.",
        category="security",
    ),
    CommandPreset(
        id="audit_firebase",
        name="[Audit] Firebase Credentials & Tokens",
        command="audit:firebase",
        description="Searches for Firebase legacy secrets, server tokens, and client credentials.",
        category="security",
    ),
    CommandPreset(
        id="audit_env_secrets",
        name="[Audit] .env Backend Password Leak",
        command="audit:env-secrets",
        description="Audits .env* for DATABASE_URL, POSTGRES_PASSWORD, and backend server keys.",
        category="security",
    ),
    CommandPreset(
        id="audit_signing_keys",
        name="[Audit] Exposed Keystore & JKS Hunt",
        command="audit:signing-keys",
        description="Checks if release keystores (.jks, .keystore, .p12) are tracked in git.",
        category="security",
    ),
    CommandPreset(
        id="audit_aws_keys",
        name="[Audit] AWS Access Key Detection",
        command="audit:aws-keys",
        description="Scans for hardcoded AWS Access Key IDs (AKIA...) in resources and assets.",
        category="security",
    ),
    CommandPreset(
        id="audit_service_accounts",
        name="[Audit] GCP Service Account JSON",
        command="audit:service-accounts",
        description="Hunts for Google Cloud service-account*.json with private keys in project.",
        category="security",
    ),
    CommandPreset(
        id="audit_private_keys",
        name="[Audit] Cryptographic Private Keys",
        command="audit:private-keys",
        description="Scans for PEM/RSA private key blocks in repository and APK assets.",
        category="security",
    ),
    CommandPreset(
        id="audit_high_entropy",
        name="[Audit] High-Entropy Secret Strings",
        command="audit:high-entropy",
        description="Calculates Shannon entropy to detect high-entropy tokens and passwords.",
        category="security",
    ),
    CommandPreset(
        id="audit_gitleaks",
        name="[Audit] Gitleaks Repository Scan",
        command="audit:gitleaks",
        description="Executes Gitleaks detection across git history to detect committed secrets.",
        category="security",
    ),
    # Gradle Builds & Assembly
    CommandPreset(
        id="assemble_debug",
        name="[Build] Assemble Debug APK",
        command=f"{_GRADLE} assembleDebug",
        description="Compiles debug APK for testing.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="assemble_release",
        name="[Build] Assemble Release APK",
        command=f"{_GRADLE} assembleRelease",
        description="Compiles production release APK.",
        category="build",
        is_release=True,
    ),
    CommandPreset(
        id="bundle_release",
        name="[Build] App Bundle (Release AAB)",
        command=f"{_GRADLE} bundleRelease",
        description="Builds production Android App Bundle (.aab) for Google Play distribution.",
        category="build",
        is_release=True,
    ),
    CommandPreset(
        id="bundle_debug",
        name="[Build] App Bundle (Debug AAB)",
        command=f"{_GRADLE} bundleDebug",
        description="Builds debug Android App Bundle (.aab) for testing bundle splitting.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="gradle_clean",
        name="[Build] Clean Project Artifacts",
        command=f"{_GRADLE} clean",
        description="Deletes build directories and temporary outputs.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="gradle_clean_cache",
        name="[Build] Clean Build Cache",
        command=f"{_GRADLE} cleanBuildCache",
        description="Clears Gradle build cache to resolve stale compilation issues.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="gradle_build",
        name="[Build] Full Build (assemble + check)",
        command=f"{_GRADLE} build",
        description="Runs a complete build including compilation, tests, and checks.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="compile_debug",
        name="[Build] Compile Debug Sources",
        command=f"{_GRADLE} compileDebugSources",
        description="Compiles Java and Kotlin source files for debug variant without packaging.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="compile_release",
        name="[Build] Compile Release Sources",
        command=f"{_GRADLE} compileReleaseSources",
        description="Compiles Java and Kotlin source files for release variant.",
        category="build",
        is_release=True,
    ),
    CommandPreset(
        id="gradle_dependencies",
        name="[Build] Print Dependency Tree",
        command=f"{_GRADLE} app:dependencies",
        description="Displays the dependency graph of the Android app module.",
        category="build",
        is_release=False,
    ),
    # Testing, Linting & Verification
    CommandPreset(
        id="gradle_test",
        name="[Test] Run All Unit Tests",
        command=f"{_GRADLE} test",
        description="Executes the full unit test suite across all build variants.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="test_debug",
        name="[Test] Run Debug Unit Tests",
        command=f"{_GRADLE} testDebugUnitTest",
        description="Runs local JVM unit tests specifically for the debug variant.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="test_release",
        name="[Test] Run Release Unit Tests",
        command=f"{_GRADLE} testReleaseUnitTest",
        description="Runs local JVM unit tests for the release variant.",
        category="build",
        is_release=True,
    ),
    CommandPreset(
        id="connected_test",
        name="[Test] Connected Device Tests",
        command=f"{_GRADLE} connectedAndroidTest",
        description="Runs instrumentation tests on an active connected Android device.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="gradle_lint",
        name="[Test] Run Android Lint Analysis",
        command=f"{_GRADLE} lint",
        description="Performs static code analysis using Android Lint to catch bugs and issues.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="lint_debug",
        name="[Test] Lint Debug Variant",
        command=f"{_GRADLE} lintDebug",
        description="Runs Android Lint analysis specifically on the debug build variant.",
        category="build",
        is_release=False,
    ),
    CommandPreset(
        id="lint_vital",
        name="[Test] Lint Vital Release Checks",
        command=f"{_GRADLE} lintVitalRelease",
        description="Executes fatal release-blocking lint checks before shipping.",
        category="build",
        is_release=True,
    ),
    CommandPreset(
        id="gradle_check",
        name="[Test] Run All Verification Tasks",
        command=f"{_GRADLE} check",
        description="Executes all verification tasks including unit tests and static checks.",
        category="build",
        is_release=False,
    ),
    # ADB & Device Management
    CommandPreset(
        id="adb_devices",
        name="[ADB] List Connected Devices",
        command="adb devices -l",
        description="Lists all USB and network connected Android devices with models.",
        category="adb",
    ),
    CommandPreset(
        id="adb_install",
        name="[ADB] Install APK to Device",
        command="adb install -r -t {apk}",
        description="Installs selected APK to connected Android device.",
        category="adb",
    ),
    CommandPreset(
        id="adb_uninstall",
        name="[ADB] Uninstall Application",
        command="adb uninstall {package}",
        description="Removes application package from the connected Android device.",
        category="adb",
    ),
    CommandPreset(
        id="adb_packages",
        name="[ADB] List 3rd-Party Packages",
        command="adb shell pm list packages -3",
        description="Lists all third-party application packages installed on the device.",
        category="adb",
    ),
    CommandPreset(
        id="adb_getprop",
        name="[ADB] Dump Device Properties",
        command="adb shell getprop",
        description="Dumps Android OS properties (model, manufacturer, SDK level, build ID).",
        category="adb",
    ),
    CommandPreset(
        id="adb_logcat",
        name="[ADB] Dump Recent Logcat",
        command="adb logcat -d",
        description="Dumps recent system and application logcat messages from connected device.",
        category="adb",
    ),
    CommandPreset(
        id="adb_logcat_clear",
        name="[ADB] Clear Logcat Buffer",
        command="adb logcat -c",
        description="Clears the device logcat buffer to start fresh logging.",
        category="adb",
    ),
    CommandPreset(
        id="adb_battery",
        name="[ADB] Check Battery Status",
        command="adb shell dumpsys battery",
        description="Queries battery level, temperature, voltage, and charging state from device.",
        category="adb",
    ),
    CommandPreset(
        id="adb_meminfo",
        name="[ADB] Check Memory Usage",
        command="adb shell dumpsys meminfo",
        description="Displays RAM usage summary and memory distribution across active processes.",
        category="adb",
    ),
    CommandPreset(
        id="adb_screencap",
        name="[ADB] Capture Screenshot",
        command="adb shell screencap -p /sdcard/droiddesk_screen.png",
        description="Captures a full resolution PNG screenshot on connected Android device.",
        category="adb",
    ),
    CommandPreset(
        id="adb_kill_server",
        name="[ADB] Restart ADB Server",
        command="adb kill-server",
        description="Kills ADB daemon server to recover from connection drops.",
        category="adb",
    ),
    # APK Inspection & Signing Analysis
    CommandPreset(
        id="apksigner_verify",
        name="[APK] Verify Signature Schemes",
        command="apksigner verify --verbose {apk}",
        description="Verifies APK signature compliance across schemes v1, v2, v3, and v4.",
        category="apk",
    ),
    CommandPreset(
        id="apksigner_certs",
        name="[APK] Print Certificate Fingerprints",
        command="apksigner verify --print-certs {apk}",
        description="Extracts signing certificates, Subject DN, SHA-1, and SHA-256 fingerprints.",
        category="apk",
    ),
    CommandPreset(
        id="aapt2_badging",
        name="[APK] Dump Package & Badging",
        command="aapt2 dump badging {apk}",
        description="Dumps package name, version code, launchable activities, and SDK levels.",
        category="apk",
    ),
    CommandPreset(
        id="aapt2_strings",
        name="[APK] Dump String Resource Pool",
        command="aapt2 dump strings {apk}",
        description="Dumps compiled string resource table from resources.arsc.",
        category="apk",
    ),
    CommandPreset(
        id="aapt2_permissions",
        name="[APK] Dump APK Permissions",
        command="aapt2 dump permissions {apk}",
        description="Extracts all dangerous, normal, and signature permissions requested by APK.",
        category="apk",
    ),
    CommandPreset(
        id="apkanalyzer_summary",
        name="[APK] Analyzer Summary",
        command="apkanalyzer apk summary {apk}",
        description="Prints APK package name, version code, and version name via APK Analyzer.",
        category="apk",
    ),
    CommandPreset(
        id="apkanalyzer_files",
        name="[APK] List Internal Archive Files",
        command="apkanalyzer files list {apk}",
        description="Lists all internal zip entries and file sizes inside the APK.",
        category="apk",
    ),
    CommandPreset(
        id="apkanalyzer_dex",
        name="[APK] Analyze DEX Method Count",
        command="apkanalyzer dex packages {apk}",
        description="Analyzes DEX classes and method counts to inspect 64k multidex limits.",
        category="apk",
    ),
    # Custom Command
    CommandPreset(
        id="custom",
        name="[Custom] Custom Command...",
        command="",
        description="Type and run any custom shell, Gradle, ADB, or SDK command.",
        category="custom",
        is_release=False,
    ),
]


class AuditWorker(QThread):
    output_line = Signal(str)
    guard_status = Signal(str, str, str)  # retained for backwards compatibility
    audit_completed = Signal(int, int)  # total_inspected, leaks_found

    def __init__(
        self,
        ctx: AppContext,
        apk_path: Path | None,
        mode: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._apk_path = apk_path
        self._mode = mode
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True
        if self._ctx.scan_service:
            self._ctx.scan_service.cancel()

    def run(self) -> None:
        self.output_line.emit("=" * 72)
        self.output_line.emit("🔍 DEFENSIVE SECURITY AUDIT: KEY EXTRACTION & HOT DATA LEAK TEST")
        self.output_line.emit("=" * 72)
        self.output_line.emit(
            f"Mode: {self._mode.upper()}\n"
            "Objective: Verify if an external attacker can steal API keys or hot data.\n"
        )

        project_root = (
            self._ctx.env_service.project_root
            if self._ctx.env_service
            else Path.cwd()
        )

        total_inspected = 0
        total_leaks = 0
        critical_leaks = 0

        # Check Environment & Properties files
        if self._mode in ("env", "project", "full") and not self._is_cancelled:
            self.output_line.emit("[*] Scanning Config & Environment files (.env*, properties)...")
            env_files: list[Path] = []
            if project_root.is_dir():
                for p in project_root.iterdir():
                    if p.is_file() and (
                        p.name.startswith(".env")
                        or p.name in ("local.properties", "gradle.properties")
                    ):
                        env_files.append(p)

            hot_patterns = {
                "DATABASE_URL": "Backend Database Connection String",
                "POSTGRES_PASSWORD": "PostgreSQL Server Password",
                "MYSQL_PASSWORD": "MySQL Database Password",
                "SECRET_KEY": "Backend Application Secret Key",
                "JWT_SECRET": "JSON Web Token Signing Secret",
                "API_SECRET": "Backend API Secret Key",
                "PRIVATE_KEY": "Cryptographic Private Key",
            }

            env_leaks = 0
            for ef in env_files:
                if self._is_cancelled:
                    break
                total_inspected += 1
                try:
                    content = ef.read_text(encoding="utf-8", errors="replace")
                    for line_no, line in enumerate(content.splitlines(), start=1):
                        clean_line = line.strip()
                        if not clean_line or clean_line.startswith("#"):
                            continue
                        for kw, label in hot_patterns.items():
                            if kw.lower() in clean_line.lower() and "=" in clean_line:
                                env_leaks += 1
                                critical_leaks += 1
                                self.output_line.emit(
                                    f"  [CRITICAL LEAK] {ef.name}:{line_no} -> {label} ({kw})"
                                )
                                self.output_line.emit(
                                    "    -> Risk: Backend credentials in client tree!\n"
                                    "    -> Defense: Never ship backend credentials.\n"
                                )
                except Exception as e:
                    self.output_line.emit(f"  [!] Error reading {ef.name}: {e}")

            if env_leaks == 0:
                self.output_line.emit("  [PASS] No raw backend secrets found in env files.\n")
            total_leaks += env_leaks

        # Check APK String Resources & Assets
        if self._mode in ("apk", "maps", "firebase", "aws", "full") and not self._is_cancelled:
            self.output_line.emit("[*] Simulating APK String Extraction (resources.arsc)...")
            if self._apk_path is None or not self._apk_path.is_file():
                if self._mode in ("apk", "maps"):
                    self.output_line.emit("  [!] No active APK selected.")
                    self.output_line.emit("      Please upload or build an APK first to audit it.")
                    self.audit_completed.emit(total_inspected, total_leaks)
                    return
                else:
                    self.output_line.emit("  [INFO] No target APK selected. Skipping APK scan.\n")
            else:
                target_apk = self._apk_path
                self.output_line.emit(f"  Target: {target_apk.name}")

                named_strings: list[tuple[str, str]] = []
                if self._ctx.apk_service and hasattr(self._ctx.apk_service, "_reader"):
                    named_strings = (
                        self._ctx.apk_service._reader.extract_named_string_resources(target_apk)
                    )
                elif self._ctx.scan_service and hasattr(self._ctx.scan_service, "_apk_reader"):
                    named_strings = (
                        self._ctx.scan_service._apk_reader.extract_named_string_resources(
                            target_apk
                        )
                    )

                self.output_line.emit(f"  Extracted {len(named_strings)} string resources.")
                total_inspected += len(named_strings)

                maps_pattern = re.compile(r"AIzaSy[A-Za-z0-9_-]{33}")
                aws_pattern = re.compile(r"\bAKIA[0-9A-Z]{16}\b")

                for res_name, val in named_strings:
                    if self._is_cancelled:
                        break
                    if maps_pattern.search(val) and self._mode in ("apk", "maps", "full"):
                        total_leaks += 1
                        key_type = (
                            "Google Maps API Key"
                            if "maps" in res_name.lower()
                            else "Google Cloud / Firebase API Key"
                        )
                        self.output_line.emit(
                            f"  [KEY DETECTED] strings.xml -> name='{res_name}'"
                        )
                        self.output_line.emit(f"    Key: {redact_secret(val)}")
                        self.output_line.emit(f"    Type: {key_type}")
                        self.output_line.emit(
                            "    Threat: Anyone decompiling this APK can extract this API key.\n"
                            "    Defense: Restrict key in Google Cloud Console with Application "
                            "Restriction:\n"
                            "             'Android apps' with Package Name and SHA-1 fingerprint.\n"
                        )
                    elif aws_pattern.search(val) and self._mode in ("apk", "aws", "full"):
                        critical_leaks += 1
                        total_leaks += 1
                        self.output_line.emit(
                            f"  [CRITICAL LEAK] AWS Key in strings.xml (name='{res_name}')"
                        )
                        self.output_line.emit(f"    Key: {redact_secret(val)}")
                        self.output_line.emit(
                            "    Defense: Remove immediately! AWS credentials must never ship in "
                            "an APK.\n"
                        )

                # Scan APK assets & raw resources via ScanService
                if self._ctx.scan_service and not self._is_cancelled:
                    apk_scan_res = self._ctx.scan_service.scan_apk(target_apk)
                    total_inspected += apk_scan_res.files_scanned
                    for finding in apk_scan_res.findings:
                        if self._is_cancelled:
                            break
                        if (
                            "strings.xml" in str(finding.file_path)
                            and "aizasy" in finding.redacted.lower()
                        ):
                            continue
                        total_leaks += 1
                        if finding.severity.value == "critical":
                            critical_leaks += 1
                        k_name = rule_id_to_key_name(finding.rule_id)
                        f_name = Path(finding.file_path).name
                        self.output_line.emit(f"  [FOUND IN APK] {k_name} in {f_name}")
                        rec = _SEVERITY_RECOMMENDATIONS.get(
                            finding.rule_id, "Restrict or remove key."
                        )
                        self.output_line.emit(f"    Defense: {rec}\n")

        # Project Repository Scan
        if (
            self._mode in ("project", "full", "signing", "gcp", "pem", "entropy", "gitleaks")
            and not self._is_cancelled
        ):
            self.output_line.emit("[*] Scanning Project Repository for Leaked Keys & Tokens...")
            if self._ctx.scan_service:
                proj_res = self._ctx.scan_service.scan_project(project_root)
                total_inspected += proj_res.files_scanned
                for finding in proj_res.findings:
                    if self._is_cancelled:
                        break
                    total_leaks += 1
                    if finding.severity.value == "critical":
                        critical_leaks += 1
                    rel_path = (
                        finding.file_path.relative_to(project_root)
                        if finding.file_path.is_relative_to(project_root)
                        else finding.file_path.name
                    )
                    k_name = rule_id_to_key_name(finding.rule_id)
                    loc_str = f"{rel_path}:{finding.line_number}"
                    self.output_line.emit(f"  [FOUND IN REPO] {k_name}: {loc_str}")
                    self.output_line.emit(f"    Matched: {redact_secret(finding.redacted)}")
                    rec = _SEVERITY_RECOMMENDATIONS.get(
                        finding.rule_id, "Restrict or remove credential."
                    )
                    self.output_line.emit(f"    Defense: {rec}\n")

                if not proj_res.findings:
                    self.output_line.emit(
                        "  [PASS] No private keys or service accounts found in project.\n"
                    )

        # Summary
        self.output_line.emit("=" * 72)
        self.output_line.emit("📊 AUDIT & PENETRATION TEST SUMMARY")
        self.output_line.emit("=" * 72)
        self.output_line.emit(f"Total files / resources inspected : {total_inspected}")
        self.output_line.emit(f"Total API keys / secrets detected : {total_leaks}")
        self.output_line.emit(f"Critical / High-risk credentials   : {critical_leaks}")

        if critical_leaks > 0:
            self.output_line.emit(
                "\nVERDICT: [CRITICAL RISK] Sensitive backend secrets or private keys detected!"
            )
            self.output_line.emit(
                "ACTION : Remove backend credentials immediately before distributing the app."
            )
        elif total_leaks > 0:
            self.output_line.emit(
                "\nVERDICT: [ATTENTION NEEDED] Public client API keys detected."
            )
            self.output_line.emit(
                "ACTION : Verify in Google Cloud / Firebase Console that keys are RESTRICTED"
            )
            self.output_line.emit(
                "         by Android Package Name and SHA-1 Certificate Fingerprint."
            )
            self.output_line.emit(
                "         With SHA-1 restriction, external attackers cannot abuse keys."
            )
        else:
            self.output_line.emit(
                "\nVERDICT: [SAFE & PROTECTED] No exposed credentials detected!"
            )

        self.output_line.emit("=" * 72)
        self.audit_completed.emit(total_inspected, total_leaks)


class CommandsPage(QWidget):
    upload_requested = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx
        self._build_service = ctx.build_service
        self._env_service = ctx.env_service
        self._apk_path: Path | None = None
        self._audit_worker: AuditWorker | None = None
        self._filtered_presets: list[CommandPreset] = list(PRESET_COMMANDS)

        self.setProperty("role", "page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader(
            "Commands & Security Audit",
            "Select from 50 built-in commands for builds, testing, security audits, "
            "ADB operations, and APK analysis. Use the search bar to filter instantly.",
        )
        outer.addWidget(header)

        # Command Preset & Execution Bar
        cmd_card = Card("Command Selection & Search")
        cmd_layout = cmd_card.body_layout()

        # Search filter bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        filter_label = QLabel("Search:")
        filter_label.setStyleSheet("font-weight: 600;")
        filter_row.addWidget(filter_label)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "Type to filter commands (e.g. map, debug, adb, test, secret)..."
        )
        self._search_input.addAction(
            get_icon("search", size=14, color=TEXT_MUTED),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search_input.textChanged.connect(self._on_filter_text_changed)
        filter_row.addWidget(self._search_input, 1)

        self._filter_count_label = QLabel(f"({len(PRESET_COMMANDS)} commands)")
        self._filter_count_label.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        filter_row.addWidget(self._filter_count_label)

        cmd_layout.addLayout(filter_row)

        # Command selection and action buttons
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        preset_label = QLabel("Command:")
        preset_label.setStyleSheet("font-weight: 600;")
        row2.addWidget(preset_label)

        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(280)
        for p in self._filtered_presets:
            cat_icon = get_icon(
                _CATEGORY_ICONS.get(p.category, "terminal"),
                size=14,
                color=_CATEGORY_COLORS.get(p.category, TEXT_MUTED),
            )
            self._preset_combo.addItem(cat_icon, p.name, p.id)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        row2.addWidget(self._preset_combo, 2)

        self._command_input = QLineEdit()
        self._command_input.setPlaceholderText("Command to execute")
        self._command_input.setMinimumWidth(220)
        self._command_action: QAction = self._command_input.addAction(
            get_icon("terminal", size=14, color=TEXT_MUTED),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._command_input.returnPressed.connect(self._on_run_clicked)
        row2.addWidget(self._command_input, 2)

        self._run_button = QPushButton("Run Security Audit")
        self._run_button.setProperty("role", "primary")
        self._run_button.setIcon(get_icon("play", size=14, color="#ffffff"))
        self._run_button.setIconSize(QSize(14, 14))
        self._run_button.clicked.connect(self._on_run_clicked)
        row2.addWidget(self._run_button)

        self._stop_button = QPushButton("Stop")
        self._stop_button.setProperty("role", "secondary")
        self._stop_button.setIcon(get_icon("square", size=13, color=TEXT_MUTED))
        self._stop_button.setIconSize(QSize(13, 13))
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._on_stop_clicked)
        row2.addWidget(self._stop_button)

        cmd_layout.addLayout(row2)

        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        self._desc_label.setProperty("role", "muted")
        cmd_layout.addWidget(self._desc_label)

        outer.addWidget(cmd_card)

        self._empty_banner = EmptyStateWidget(
            title="No Active APK Selected",
            message=(
                "Build commands generate new APK artifacts. You can run build commands "
                "now, or upload an existing APK to inspect and audit immediately."
            ),
            button_text="Upload APK",
            compact=True,
        )
        self._empty_banner.upload_requested.connect(self.upload_requested.emit)
        outer.addWidget(self._empty_banner)

        # Output panel takes full remaining space
        outer.addWidget(self._build_output_panel(), 1)

        if self._build_service:
            self._build_service.guard_evaluated.connect(self._on_guard_evaluated)
            self._build_service.output_line.connect(self._on_output_line)
            self._build_service.command_finished.connect(self._on_command_finished)

        # Initialize to first preset
        self._on_preset_changed(0)
        self.set_apk(None)

    def set_apk(self, path: Path | None) -> None:
        self._apk_path = path
        if path is None:
            self._empty_banner.show()
        else:
            self._empty_banner.hide()

    def _on_filter_text_changed(self, text: str) -> None:
        query = text.strip().lower()
        self._filtered_presets = [
            p
            for p in PRESET_COMMANDS
            if not query
            or query in p.name.lower()
            or query in p.command.lower()
            or query in p.description.lower()
        ]

        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        for p in self._filtered_presets:
            cat_icon = get_icon(
                _CATEGORY_ICONS.get(p.category, "terminal"),
                size=14,
                color=_CATEGORY_COLORS.get(p.category, TEXT_MUTED),
            )
            self._preset_combo.addItem(cat_icon, p.name, p.id)
        self._preset_combo.blockSignals(False)

        count = len(self._filtered_presets)
        self._filter_count_label.setText(f"({count} of {len(PRESET_COMMANDS)})")

        if self._filtered_presets:
            self._preset_combo.setCurrentIndex(0)
            self._on_preset_changed(0)
        else:
            self._command_input.clear()
            self._desc_label.setText("No commands match your filter.")
            self._run_button.setEnabled(False)

    def _on_preset_changed(self, index: int) -> None:
        if 0 <= index < len(self._filtered_presets):
            self._run_button.setEnabled(True)
            preset = self._filtered_presets[index]
            cmd = preset.command
            if "{apk}" in cmd and self._apk_path:
                cmd = cmd.replace("{apk}", f'"{self._apk_path}"')

            self._command_input.setText(cmd)
            self._desc_label.setText(preset.description)

            cat_icon = get_icon(
                _CATEGORY_ICONS.get(preset.category, "terminal"),
                size=14,
                color=_CATEGORY_COLORS.get(preset.category, TEXT_MUTED),
            )
            if hasattr(self, "_command_action"):
                self._command_action.setIcon(cat_icon)

            if preset.category == "security":
                self._command_input.setReadOnly(True)
                self._command_input.setStyleSheet("color: #a1a1aa; background-color: #1c1d22;")
                self._run_button.setText("Run Security Audit")
            elif preset.category == "build":
                self._command_input.setReadOnly(False)
                self._command_input.setStyleSheet("")
                if preset.is_release:
                    self._run_button.setText("Run Release Build")
                else:
                    self._run_button.setText("Run Command")
            elif preset.category in ("adb", "apk"):
                self._command_input.setReadOnly(False)
                self._command_input.setStyleSheet("")
                self._run_button.setText("Run Command")
            else:  # custom
                self._command_input.setReadOnly(False)
                self._command_input.setStyleSheet("")
                self._command_input.setPlaceholderText(
                    "Enter custom command (e.g. ./gradlew assembleDebug)"
                )
                self._run_button.setText("Run Custom Command")

    def _build_output_panel(self) -> QWidget:
        card = Card("Output Console")
        top_bar = QHBoxLayout()
        top_bar.addStretch(1)
        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("role", "secondary")
        clear_btn.clicked.connect(self._clear_console)
        top_bar.addWidget(clear_btn)
        card.body_layout().addLayout(top_bar)

        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setPlaceholderText(
            "Live build output and security audit findings appear here..."
        )
        self._console.setStyleSheet("""
            QPlainTextEdit {
                font-family: 'Cascadia Mono', 'Consolas', monospace;
                font-size: 12px;
                background-color: #0f1012;
                color: #e4e4e7;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        card.body_layout().addWidget(self._console, 1)
        return card

    def _clear_console(self) -> None:
        self._console.clear()

    def _on_guard_evaluated(self, guard: GuardResult) -> None:
        pass

    def _on_output_line(self, line: str) -> None:
        self._console.appendPlainText(line)
        sb = self._console.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def _on_command_finished(self, exit_code: int) -> None:
        self._console.appendPlainText(f"\n[Command exited with status {exit_code}]")
        self._run_button.setEnabled(True)
        self._stop_button.setEnabled(False)

    def _on_audit_finished(self, total_inspected: int, leaks_found: int) -> None:
        self._run_button.setEnabled(True)
        self._stop_button.setEnabled(False)

    def _on_stop_clicked(self) -> None:
        if self._audit_worker and self._audit_worker.isRunning():
            self._audit_worker.cancel()
            self._console.appendPlainText("\n[Security audit cancelled by user]")
            self._run_button.setEnabled(True)
            self._stop_button.setEnabled(False)
            return

        if self._build_service:
            self._build_service.stop()
            self._console.appendPlainText("\n[Process cancelled by user]")
            self._run_button.setEnabled(True)
            self._stop_button.setEnabled(False)

    def _on_run_clicked(self) -> None:
        idx = self._preset_combo.currentIndex()
        preset = self._filtered_presets[idx] if 0 <= idx < len(self._filtered_presets) else None

        if preset and preset.category == "security":
            self._run_security_audit(preset)
        else:
            self._run_build_command(preset)

    def _run_security_audit(self, preset: CommandPreset) -> None:
        self._console.clear()

        # Map preset ID to specific audit mode
        mode_map = {
            "audit_apk_keys": "apk",
            "audit_project_secrets": "project",
            "audit_full_pentest": "full",
            "audit_maps_keys": "maps",
            "audit_firebase": "firebase",
            "audit_env_secrets": "env",
            "audit_signing_keys": "signing",
            "audit_aws_keys": "aws",
            "audit_service_accounts": "gcp",
            "audit_private_keys": "pem",
            "audit_high_entropy": "entropy",
            "audit_gitleaks": "gitleaks",
        }
        mode = mode_map.get(preset.id, "full")

        self._run_button.setEnabled(False)
        self._stop_button.setEnabled(True)

        self._audit_worker = AuditWorker(
            ctx=self._ctx,
            apk_path=self._apk_path,
            mode=mode,
            parent=self,
        )
        self._audit_worker.output_line.connect(self._on_output_line)
        self._audit_worker.audit_completed.connect(self._on_audit_finished)
        self._audit_worker.start()

    def _run_build_command(self, preset: CommandPreset | None) -> None:
        if not self._build_service:
            return

        cmd_text = self._command_input.text().strip()
        if not cmd_text:
            return

        # Substitute {apk} placeholder if present
        if "{apk}" in cmd_text:
            if self._apk_path:
                cmd_text = cmd_text.replace("{apk}", f'"{self._apk_path}"')
            else:
                self._console.clear()
                self._console.appendPlainText(
                    "[!] This command requires an active APK artifact.\n"
                    "    Please upload or select an APK first."
                )
                return

        # Substitute {package} placeholder if present
        if "{package}" in cmd_text:
            pkg = "com.example.app"
            if self._apk_path and self._ctx.apk_service:
                try:
                    info = self._ctx.apk_service.inspect(self._apk_path)
                    pkg = info.package_name
                except Exception:
                    pass
            cmd_text = cmd_text.replace("{package}", pkg)

        try:
            tokens = shlex.split(cmd_text)
        except Exception:
            tokens = cmd_text.split()

        if not tokens:
            return

        # Resolve SDK tools if applicable (adb, apksigner, aapt2, apkanalyzer, gitleaks)
        if tokens[0] in ("adb", "aapt2", "apksigner", "apkanalyzer", "gitleaks"):
            try:
                resolved = self._ctx.tool_locator.resolve(tokens[0])
                tokens[0] = str(resolved)
            except Exception:
                pass

        active_env = self._env_service.active_environment() if self._env_service else None
        project_root = self._env_service.project_root if self._env_service else Path.cwd()

        profile = CommandProfile(
            name=tokens[0],
            command=tokens,
            required_environment=active_env.key if active_env else None,
            guard_environment_matches=False,
            guard_release_allowed=False,
            guard_git_clean=False,
            guard_secret_scan_clean=False,
            guard_no_debug_flags=False,
            guard_version_bumped=False,
        )

        self._console.clear()
        self._run_button.setEnabled(False)
        self._stop_button.setEnabled(True)
        self._console.appendPlainText(f">>> Running: {' '.join(profile.command)}\n")

        try:
            self._build_service.run(
                profile=profile,
                cwd=project_root,
                override_note=None,
                apk_path=self._apk_path,
            )
        except Exception as e:
            self._console.appendPlainText(f"\n[EXECUTION ERROR] {e}")
            self._run_button.setEnabled(True)
            self._stop_button.setEnabled(False)
