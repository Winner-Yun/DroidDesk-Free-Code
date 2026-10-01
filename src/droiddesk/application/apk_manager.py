"""APK Manager.

Handles APK inspection, installation, launching, and uninstallation across devices.
"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from droiddesk.core.models import ApkInfo
from droiddesk.infra.adb import AdbClient
from droiddesk.infra.apk_reader import ApkReader
from droiddesk.infra.tools import ToolLocator


class ApkManager:
    """Manages APK lifecycle (validation, installation, launching, removal)."""

    def __init__(
        self,
        adb_client: AdbClient,
        apk_reader: ApkReader | None = None,
        tool_locator: ToolLocator | None = None,
    ) -> None:
        self._adb = adb_client
        self._apk_reader = apk_reader or ApkReader(tool_locator=tool_locator)
        self._tool_locator = tool_locator

    def inspect_apk(self, apk_path: Path) -> ApkInfo:
        """Inspect APK to extract package name, version, and manifest details."""
        if not apk_path.is_file():
            raise FileNotFoundError(f"APK file not found: {apk_path}")
        return self._apk_reader.inspect_fast(apk_path)

    def find_launchable_activity(self, apk_path: Path) -> str | None:
        """Detect the launchable activity of an APK using pyaxmlparser / androguard."""
        try:
            import pyaxmlparser

            apk = pyaxmlparser.APK(str(apk_path))
            main_activity = apk.get_main_activity()
            if main_activity:
                return str(main_activity)
        except Exception:
            pass

        # Fallback to full inspection via ApkReader
        try:
            full_info = self._apk_reader.inspect_full(apk_path)
            for act in full_info.activities:
                if "main" in act.lower() or "splash" in act.lower() or "home" in act.lower():
                    return act
            if full_info.activities:
                return full_info.activities[0]
        except Exception:
            pass

        return None

    def install_apk(
        self,
        serial: str,
        apk_path: Path,
        replace: bool = True,
        test_ok: bool = True,
    ) -> tuple[bool, str]:
        """Install an APK onto a device by serial number."""
        if not apk_path.is_file():
            return False, f"APK file not found: {apk_path}"

        args = ["-s", serial, "install"]
        if replace:
            args.append("-r")
        if test_ok:
            args.append("-t")
        args.append(str(apk_path))

        logger.info(f"Installing {apk_path.name} on {serial}...")
        try:
            res = self._adb._runner.run(self._adb.adb_path, args, timeout=120.0)
            output = (res.stdout + "\n" + res.stderr).strip()

            if "Success" in output:
                logger.info(f"Successfully installed {apk_path.name} on {serial}")
                return True, "APK installed successfully."
            else:
                # Parse specific error failure code
                m_fail = re.search(r"Failure\s*\[([^\]]+)\]", output)
                fail_reason = m_fail.group(1) if m_fail else output
                error_msg = self._explain_install_failure(fail_reason)
                logger.warning(f"Install failed on {serial}: {error_msg}")
                return False, error_msg
        except Exception as exc:
            return False, f"Installation error: {exc}"

    def launch_app(
        self,
        serial: str,
        package_name: str,
        activity_name: str | None = None,
    ) -> tuple[bool, str]:
        """Launch an application on the device using activity manager or monkey."""
        clean_pkg = package_name.strip()
        if not clean_pkg:
            return False, "Package name cannot be empty."

        logger.info(f"Launching app '{clean_pkg}' on {serial} (activity={activity_name})...")

        # 1. Try explicit activity launch if provided
        if activity_name:
            clean_act = activity_name.strip()
            # If relative, prepend package
            if clean_act.startswith("."):
                target = f"{clean_pkg}/{clean_act}"
            elif "/" in clean_act:
                target = clean_act
            else:
                target = f"{clean_pkg}/{clean_act}"

            res = self._adb._runner.run(
                self._adb.adb_path,
                ["-s", serial, "shell", "am", "start", "-n", target],
                timeout=15.0,
            )
            output = res.stdout + res.stderr
            if "Error" not in output and "Exception" not in output:
                return True, f"Application launched: {clean_pkg}"

        # 2. Fallback to monkey launch (standard Android launcher action)
        res = self._adb._runner.run(
            self._adb.adb_path,
            [
                "-s",
                serial,
                "shell",
                "monkey",
                "-p",
                clean_pkg,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            timeout=15.0,
        )
        output = res.stdout + res.stderr
        if res.exit_code == 0 and "Events injected: 1" in output:
            return True, f"Application launched: {clean_pkg}"
        elif "No activities found" in output:
            return False, f"No launchable activity found for package '{clean_pkg}'."

        return False, f"Failed to launch application: {output.strip()}"

    def uninstall_app(self, serial: str, package_name: str) -> tuple[bool, str]:
        """Uninstall an application from the device."""
        res = self._adb._runner.run(
            self._adb.adb_path,
            ["-s", serial, "uninstall", package_name],
            timeout=30.0,
        )
        if "Success" in res.stdout:
            return True, f"Application '{package_name}' uninstalled."
        return False, f"Uninstall failed: {res.stdout.strip() or res.stderr.strip()}"

    def is_app_installed(self, serial: str, package_name: str) -> bool:
        """Check whether a package is currently installed on the device."""
        try:
            res = self._adb._runner.run(
                self._adb.adb_path,
                ["-s", serial, "shell", "pm", "list", "packages", package_name],
                timeout=5.0,
            )
            return f"package:{package_name}" in res.stdout
        except Exception:
            return False

    def _explain_install_failure(self, failure_code: str) -> str:
        code = failure_code.strip()
        explanations = {
            "INSTALL_FAILED_ALREADY_EXISTS": (
                "An application with this package name already exists with a different signature."
            ),
            "INSTALL_FAILED_INSUFFICIENT_STORAGE": (
                "The device does not have enough storage space to install this application."
            ),
            "INSTALL_FAILED_UPDATE_INCOMPATIBLE": (
                "Signatures do not match the previously installed version."
            ),
            "INSTALL_FAILED_OLDER_SDK": (
                "The application's minimum SDK is higher than the device's Android version."
            ),
            "INSTALL_FAILED_CPU_ABI_INCOMPATIBLE": (
                "The APK does not contain native libraries compatible with "
                "this device's CPU architecture."
            ),
            "INSTALL_FAILED_TEST_ONLY": (
                "The APK is built with test-only flag. Enable test install (-t)."
            ),
            "INSTALL_PARSE_FAILED_BAD_MANIFEST": (
                "Android could not parse the APK's AndroidManifest.xml."
            ),
            "INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES": (
                "The APK's signing certificates are inconsistent or corrupted."
            ),
        }
        explanation = explanations.get(code)
        if explanation:
            return f"{code}: {explanation}"
        return f"Install failed: {code}"
