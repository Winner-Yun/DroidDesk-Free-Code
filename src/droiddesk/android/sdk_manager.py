"""Android SDK Environment Manager: detects, validates, and manages Android SDK tools."""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from droiddesk.android.command_runner import CommandRunner
from droiddesk.android.models import AndroidEnvState, AndroidEnvStatus
from droiddesk.config import Settings
from droiddesk.core.errors import ToolNotFoundError
from droiddesk.infra.tools import ToolLocator


class AndroidSdkManager:
    """Manages discovery, validation, and configuration of the Android SDK environment."""

    def __init__(
        self,
        settings: Settings,
        tool_locator: ToolLocator,
        runner: CommandRunner | None = None,
    ) -> None:
        self._settings = settings
        self._tool_locator = tool_locator
        self._runner = runner or CommandRunner(tool_locator)

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def tool_locator(self) -> ToolLocator:
        return self._tool_locator

    def detect_sdk_root(self) -> Path | None:
        """Find the Android SDK root directory from settings, env, or common locations."""
        if self._settings.android_sdk_path and self._settings.android_sdk_path.is_dir():
            return self._settings.android_sdk_path

        for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            val = os.environ.get(env_var)
            if val and Path(val).is_dir():
                return Path(val)

        local_app_data = os.environ.get("LOCALAPPDATA")
        candidates = [
            Path(local_app_data) / "Android" / "Sdk" if local_app_data else None,
            Path(r"C:\Android\Sdk"),
            Path(r"C:\Android\sdk"),
            Path.home() / "AppData" / "Local" / "Android" / "Sdk",
        ]
        for cand in candidates:
            if cand and cand.is_dir():
                return cand

        # Try locating adb and inferring sdk root from parent directory
        try:
            adb_path = self._tool_locator.resolve("adb")
            if adb_path.parent.name == "platform-tools" and adb_path.parent.parent.is_dir():
                return adb_path.parent.parent
        except ToolNotFoundError:
            pass

        return None

    def check_environment(self) -> AndroidEnvStatus:
        """Thoroughly check all Android tools and return comprehensive AndroidEnvStatus."""
        self._tool_locator.invalidate_cache()
        sdk_root = self.detect_sdk_root()

        adb_path = self._resolve_safe("adb")
        emulator_path = self._resolve_safe("emulator")
        avdmanager_path = self._resolve_safe("avdmanager")
        sdkmanager_path = self._resolve_safe("sdkmanager")
        java_home = self._tool_locator.find_java_home()

        adb_version: str | None = None
        if adb_path:
            adb_info = self._tool_locator.verify_tool("adb")
            adb_version = adb_info.version

        emulator_version: str | None = None
        if emulator_path:
            emu_info = self._tool_locator.verify_tool("emulator")
            emulator_version = emu_info.version

        sdkmanager_version: str | None = None
        if sdkmanager_path:
            sdkm_info = self._tool_locator.verify_tool("sdkmanager")
            sdkmanager_version = sdkm_info.version

        # Determine Environment State
        state = AndroidEnvState.READY
        error_msg: str | None = None

        if not sdk_root:
            state = AndroidEnvState.MISSING_SDK
            error_msg = "Android SDK directory not found. Please specify your Android SDK location."
        elif not adb_path:
            state = AndroidEnvState.MISSING_ADB
            error_msg = "ADB (Android Debug Bridge) is missing. Install Android SDK Platform-Tools."
        elif not emulator_path:
            state = AndroidEnvState.MISSING_EMULATOR
            error_msg = (
                "Android Emulator is missing. "
                "Install the Emulator component via Android Studio or SDK Manager."
            )
        elif not avdmanager_path:
            state = AndroidEnvState.MISSING_AVDMANAGER
            error_msg = "AVD Manager is missing. Install Android SDK Command-line Tools."
        elif not java_home and (avdmanager_path or sdkmanager_path):
            state = AndroidEnvState.PARTIAL
            error_msg = (
                "Java runtime (JRE/JDK) is missing. Set JAVA_HOME or install Android Studio JBR."
            )

        details: dict[str, str] = {
            "SDK Root": str(sdk_root) if sdk_root else "Not detected",
            "ADB": f"{adb_path.name} ({adb_version or 'detected'})" if adb_path else "Missing",
            "Emulator": f"{emulator_path.name} ({emulator_version or 'detected'})"
            if emulator_path
            else "Missing",
            "AVD Manager": str(avdmanager_path) if avdmanager_path else "Missing",
            "SDK Manager": f"{sdkmanager_path.name} ({sdkmanager_version or 'detected'})"
            if sdkmanager_path
            else "Missing",
            "Java Home": str(java_home) if java_home else "Missing",
        }

        status = AndroidEnvStatus(
            state=state,
            sdk_root=sdk_root,
            adb_path=adb_path,
            emulator_path=emulator_path,
            avdmanager_path=avdmanager_path,
            sdkmanager_path=sdkmanager_path,
            java_home=java_home,
            adb_version=adb_version,
            emulator_version=emulator_version,
            sdkmanager_version=sdkmanager_version,
            details=details,
            error_message=error_msg,
        )
        logger.info(f"Android environment evaluated: state={state.value}, sdk_root={sdk_root}")
        return status

    def set_sdk_path(self, path: Path) -> AndroidEnvStatus:
        """Update user-configured SDK path, persist to config, and revalidate."""
        if not path.is_dir():
            raise FileNotFoundError(f"Specified SDK path does not exist: {path}")

        self._settings.android_sdk_path = path
        self._settings.save()
        self._tool_locator.invalidate_cache()
        return self.check_environment()

    def _resolve_safe(self, tool_name: str) -> Path | None:
        try:
            return self._tool_locator.resolve(tool_name)
        except ToolNotFoundError:
            return None
