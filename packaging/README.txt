
  DROIDDESK - Local Android Development Companion
  Version 1.0.0 (Windows 64-bit)


Thank you for choosing DroidDesk!

DroidDesk is a local, desktop companion designed for Android developers, QA
engineers, and security reviewers. It unifies device management, real-time
log streaming, deep APK inspection, automated smoke testing, offline credential
and secret scanning, environment switching, and build guard verification into a
single, cohesive workstation tool.

DroidDesk operates under a strict "Local-First" architecture:
- 100% Offline: Runs completely on your local machine.
- Zero Telemetry: No user accounts, tracking, or network telemetry.
- Private Data: Your source code, APKs, test logs, and credentials never
  leave your development workstation.

1. SYSTEM REQUIREMENTS & PREREQUISITES

OPERATING SYSTEM:
- Microsoft Windows 10 or Windows 11 (64-bit / x64 architecture).

HARDWARE RECOMMENDATIONS:
- Processor: Dual-core 2.0 GHz or higher (Quad-core recommended).
- Memory (RAM): Minimum 4 GB (8 GB or higher recommended).
- Storage: 500 MB free disk space for application files and local database.

EXTERNAL TOOLCHAIN REQUIREMENTS:
DroidDesk interfaces with official Android SDK command-line utilities.

- Android SDK Tools (Required for full device and APK functionality):
  * adb (Android Debug Bridge)
  * aapt2 (Android Asset Packaging Tool)
  * apksigner (APK Signature Verification Tool)
  * apkanalyzer (Optional)
  * bundletool (Optional, for Android App Bundle operations)

  * Automatic Detection:
    DroidDesk automatically locates these tools if you have Android Studio
    or the standalone Android SDK installed, or if ANDROID_HOME /
    ANDROID_SDK_ROOT environment variables are set.
  * Manual Configuration:
    If your SDK is located in a custom directory, you can specify its
    path at any time in DroidDesk under:
    Settings -> Tool Locator -> Android SDK Path.

- Secret Scanner (Pre-bundled):
  * Gitleaks is pre-bundled with DroidDesk for fast, offline credential
    detection. No separate installation is necessary.

- Screen Mirroring (Optional):
  * scrcpy: If installed and added to PATH or configured in Settings,
    DroidDesk can trigger real-time low-latency device mirroring.

2. KEY FEATURES & CAPABILITIES

* DEVICE CONTROL & MONITORING
  - Live discovery of connected physical Android devices and emulators.
  - Quick-glance device details: model, ABI architecture, Android version,
    API level, battery status, and developer options.
  - One-click ADB server restart and device reconnection.
  - Instant screen capture with automatic PNG saving and history browsing.

* REAL-TIME LOGCAT VIEWER
  - High-performance, zero-freeze log streaming from selected devices.
  - Instant search and regular expression (regex) filtering.
  - Severity level filtering (Verbose, Debug, Info, Warn, Error, Assert).
  - Stream pause, buffer clear, and log excerpt export.

* DEEP APK INSPECTION & ANALYSIS
  - Drag-and-drop any APK file to instantly inspect package manifest details.
  - Manifest viewer: package name, version name, version code, min/target SDK.
  - Component breakdown: Activities, Services, Broadcast Receivers, Providers.
  - Permissions audit: lists requested permissions with highlighted
    dangerous / sensitive capabilities.
  - Certificate & Signature Inspector: validates APK Signature Scheme
    (v1, v2, v3, and v4), MD5/SHA-1/SHA-256 fingerprints, and issuer info.

* AUTOMATED APK TEST RUNNER & QA VERDICT
  - Repeatable test cycles: Install -> Launch -> Observe -> Screenshot ->
    Logcat Crash Detection -> Auto-Uninstall.
  - Automated crash detection parsing logcat FATAL EXCEPTION and ANR traces.
  - Exportable, professional HTML and PDF test execution reports.

* OFFLINE SECURITY & SECRET SCANNING
  - Project directory and APK scanning for accidentally committed secrets.
  - Built-in detection for API keys, AWS credentials, private keys, database
    connection strings, and high-entropy secret tokens.
  - Fine-grained suppression management (.droiddesk/suppressions.toml) to
    safely silence verified false positives.

* ENVIRONMENT SWITCHING & BUILD GUARDS
  - Fast switching between project environments (e.g., Development, Staging,
    and Production) with clear visual color-coded risk indicators.
  - Pre-flight build safety gates to prevent deploying debug or compromised
    builds with hard-blocked rules.

* BUILD ARTIFACT & APK ORGANIZER
  - Rules-based file organization for output builds and APK downloads.
  - Fast duplicate detection powered by xxHash / SHA-256 content hashing.
  - Non-destructive execution with an undoable file operation journal.


3. INSTALLATION DETAILS & FILE LOCATIONS

APPLICATION DIRECTORY:
  Default: C:\Program Files\DroidDesk
  All application executables, libraries, and bundled resources are stored
  here. This directory is kept read-only during normal operation.

USER DATA & CONFIGURATION (Stored in user-writable directories):
- Configuration:
  %APPDATA%\DroidDesk\config.toml
  (Stores tool paths, device polling preferences, and UI theme options)

- Database & Persistent Cache:
  %LOCALAPPDATA%\DroidDesk\droiddesk.db
  (Stores local SQLite metadata, APK scan history, and test run records)

FILE ASSOCIATIONS:
- DroidDesk registers an optional Windows file association for .apk files.
  Double-clicking any APK file in Windows File Explorer can directly open
  and analyze it in DroidDesk.

LONG PATH SUPPORT:
- DroidDesk automatically handles extended Windows path names (>260 chars)
  common in deep Android, Gradle, and Flutter build outputs.

4. GETTING STARTED IN 4 EASY STEPS

Step 1: LAUNCH DROIDDESK
  Launch DroidDesk from your Start Menu or Desktop shortcut.

Step 2: CONNECT AN ANDROID DEVICE
  Enable "Developer Options" and "USB Debugging" on your physical phone or
  tablet, then plug it into your computer via USB (or start an Android
  Virtual Device emulator). When prompted on your phone screen, check
  "Always allow from this computer" and tap "Allow".

Step 3: VERIFY YOUR TOOLCHAIN
  Navigate to "Settings" in the DroidDesk sidebar. Check that ADB and the
  Android SDK are detected with green status badges. If needed, click
  "Browse" to specify your Android SDK path.

Step 4: ANALYZE OR TEST
  Drag and drop an .apk file into DroidDesk to inspect its contents, or
  switch to "APK Tester" to run an automated installation and launch cycle.

5. TROUBLESHOOTING & COMMON QUESTIONS

Q: My device shows as "Unauthorized" or "Offline".
A: Unlock your Android phone and accept the USB Debugging RSA authorization
   prompt. If the prompt does not appear, disconnect and reconnect the USB
   cable, or click "Reconnect" in the DroidDesk Devices page.

Q: "No Android SDK installation was automatically detected."
A: If you have Android Studio installed, your SDK is typically located at:
   C:\Users\<YourUsername>\AppData\Local\Android\Sdk
   Open DroidDesk Settings, paste this path into the "Android SDK Path" field,
   and click "Save".

Q: How do I cleanly uninstall DroidDesk?
A: Go to Windows Settings -> Apps -> Installed Apps (or Control Panel ->
   Programs and Features), select "DroidDesk", and click "Uninstall".
   Your personal settings in %APPDATA%\DroidDesk and SQLite records in
   %LOCALAPPDATA%\DroidDesk will remain intact unless manually removed.

6. DISCLAIMER & SECURITY NOTICE

DroidDesk is a local development companion and quality assurance tool.
The security and secret scanner is designed to assist developers in finding
common accidental exposures (such as uncommitted API keys or misconfigured
manifest flags); it does not constitute a formal penetration test or a
guarantee against sophisticated obfuscation or malice. Always conduct formal
security assessments prior to production release.

(C) DroidDesk. All rights reserved.

