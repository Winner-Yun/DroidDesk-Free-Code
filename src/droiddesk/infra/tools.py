"""ToolLocator: resolve adb, aapt2, apksigner, apkanalyzer, bundletool, gitleaks,
scrcpy, and git. See Section 3.1 for the discovery order, which every method here
must follow:

  1. Explicit path stored in the user's configuration file.
  2. ANDROID_HOME / ANDROID_SDK_ROOT, walking into platform-tools, build-tools
     (highest version), and cmdline-tools.
  3. Default Windows install location: %LOCALAPPDATA%\\Android\\Sdk.
  4. System PATH.
  5. If unresolved: caller shows a blocking setup dialog with a folder picker.

Results are cached and re-verified only on cache miss or version change.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from droiddesk.config import Settings
from droiddesk.core.errors import ToolNotFoundError

_KNOWN_TOOLS = (
    "adb",
    "aapt2",
    "apksigner",
    "apkanalyzer",
    "bundletool",
    "gitleaks",
    "scrcpy",
    "git",
)


class ToolLocator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, Path | None] = {}

    def resolve(self, tool_name: str) -> Path:
        """Return the resolved path for `tool_name`, raising ToolNotFoundError if
        it cannot be found anywhere in the discovery chain.
        """
        if tool_name in self._cache and self._cache[tool_name] is not None:
            return self._cache[tool_name]  # type: ignore[return-value]

        path = (
            self._from_settings(tool_name)
            or self._from_sdk_env(tool_name)
            or self._from_default_sdk_location(tool_name)
            or self._from_system_path(tool_name)
        )
        self._cache[tool_name] = path
        if path is None:
            raise ToolNotFoundError(tool_name)
        return path

    def is_available(self, tool_name: str) -> bool:
        try:
            self.resolve(tool_name)
        except ToolNotFoundError:
            return False
        return True

    def _from_settings(self, tool_name: str) -> Path | None:
        attr = f"{tool_name}_path"
        return getattr(self._settings, attr, None)

    def _from_sdk_env(self, tool_name: str) -> Path | None:
        sdk_root = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if not sdk_root:
            return None
        return self._search_sdk_root(Path(sdk_root), tool_name)

    def _from_default_sdk_location(self, tool_name: str) -> Path | None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return None
        return self._search_sdk_root(Path(local_app_data) / "Android" / "Sdk", tool_name)

    def _search_sdk_root(self, sdk_root: Path, tool_name: str) -> Path | None:
        if not sdk_root.is_dir():
            return None

        exe = f"{tool_name}.exe" if tool_name in ("adb",) else f"{tool_name}.bat"
        candidates = [
            sdk_root / "platform-tools" / exe,
            sdk_root / "platform-tools" / f"{tool_name}.exe",
        ]
        build_tools = sdk_root / "build-tools"
        if build_tools.is_dir():
            versions = sorted(build_tools.iterdir(), reverse=True)
            candidates += [v / f"{tool_name}.exe" for v in versions]
            candidates += [v / f"{tool_name}.bat" for v in versions]
        cmdline_tools = sdk_root / "cmdline-tools"
        if cmdline_tools.is_dir():
            for sub in cmdline_tools.iterdir():
                candidates.append(sub / "bin" / f"{tool_name}.bat")

        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def _from_system_path(self, tool_name: str) -> Path | None:
        found = shutil.which(tool_name)
        return Path(found) if found else None

    def find_java_home(self) -> Path | None:
        """Locate a Java runtime home directory (Android Studio JBR or JDK)."""
        exe_name = "java.exe" if os.name == "nt" else "java"
        if os.environ.get("JAVA_HOME"):
            cand = Path(os.environ["JAVA_HOME"])
            if (cand / "bin" / exe_name).is_file():
                return cand

        candidates: list[Path] = [
            Path(r"C:\Program Files\Android\Android Studio\jbr"),
            Path(r"C:\Program Files\Android\Android Studio\jre"),
            Path(r"C:\Program Files (x86)\Android\Android Studio\jbr"),
            Path(r"C:\Android\Android Studio\jbr"),
        ]

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Android" / "jbr")
            candidates.append(Path(local_app_data) / "Android" / "Sdk" / "jbr")

        prog_java = Path(r"C:\Program Files\Java")
        if prog_java.is_dir():
            candidates.extend(sorted(prog_java.glob("jdk*"), reverse=True))

        for cand in candidates:
            if (cand / "bin" / exe_name).is_file():
                return cand
        return None

    def execution_env(self) -> dict[str, str]:
        """Return environment variables with JAVA_HOME and PATH configured for tools."""
        env = os.environ.copy()
        exe_name = "java.exe" if os.name == "nt" else "java"
        jh_val = env.get("JAVA_HOME")
        if not jh_val or not (Path(jh_val) / "bin" / exe_name).is_file():
            found_jh = self.find_java_home()
            if found_jh:
                env["JAVA_HOME"] = str(found_jh)
                bin_dir = str(found_jh / "bin")
                sep = ";" if os.name == "nt" else ":"
                env["PATH"] = f"{bin_dir}{sep}{env.get('PATH', '')}"
        return env
