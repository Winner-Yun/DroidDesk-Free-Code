"""ToolLocator: resolve adb, aapt2, apksigner, apkanalyzer, bundletool, gitleaks,
scrcpy, and git. See Section 3.1 for the discovery order, which every method here
must follow:

  1. Explicit path stored in the user's configuration file.
  2. ANDROID_HOME / ANDROID_SDK_ROOT, walking into platform-tools, build-tools
     (highest version), and cmdline-tools.
  3. Default Windows install location: %LOCALAPPDATA%\\Android\\Sdk.
  4. System PATH.
  5. Bundled gitleaks.exe (or bundled tools).
  6. If unresolved: caller shows a blocking setup dialog with a folder picker.

Results are cached and re-verified only on cache miss, settings change, or manual invalidation.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
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

_JAVA_DEPENDENT_TOOLS = ("apkanalyzer", "bundletool", "apksigner")


@dataclass(frozen=True, slots=True)
class ToolInfo:
    name: str
    path: Path | None
    version: str | None
    is_bundled: bool
    is_valid: bool
    error_message: str | None


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
            or self._from_configured_sdk(tool_name)
            or self._from_sdk_env(tool_name)
            or self._from_default_sdk_location(tool_name)
            or self._from_system_path(tool_name)
            or self._from_bundled(tool_name)
        )
        self._cache[tool_name] = path
        if path is None:
            raise ToolNotFoundError(tool_name)
        return path

    def invalidate_cache(self) -> None:
        """Clear resolved path cache so settings changes apply immediately."""
        self._cache.clear()

    def is_available(self, tool_name: str) -> bool:
        try:
            self.resolve(tool_name)
        except ToolNotFoundError:
            return False
        return True

    def is_bundled(self, tool_name: str) -> bool:
        """Return True if the resolved tool resides in the bundled resources."""
        try:
            resolved = self.resolve(tool_name)
            bundled = self._from_bundled(tool_name)
            return bundled is not None and resolved.resolve() == bundled.resolve()
        except ToolNotFoundError:
            return False

    def discover_all(self) -> dict[str, bool]:
        """Check availability of all known tools without raising ToolNotFoundError."""
        return {tool_name: self.is_available(tool_name) for tool_name in _KNOWN_TOOLS}

    def verify_tool(self, tool_name: str) -> ToolInfo:
        """Actively verify tool resolution, execution, and version string."""
        try:
            path = self.resolve(tool_name)
        except ToolNotFoundError:
            return ToolInfo(
                name=tool_name,
                path=None,
                version=None,
                is_bundled=False,
                is_valid=False,
                error_message=f"'{tool_name}' not found in SDK or PATH",
            )

        is_bundled = self.is_bundled(tool_name)
        java_dependent = tool_name in _JAVA_DEPENDENT_TOOLS

        # Verify Java availability for Java-dependent tools
        if java_dependent:
            jh = self.find_java_home()
            exe_name = "java.exe" if os.name == "nt" else "java"
            has_java = (
                (jh is not None and (jh / "bin" / exe_name).is_file())
                or shutil.which("java") is not None
            )
            if not has_java:
                return ToolInfo(
                    name=tool_name,
                    path=path,
                    version=None,
                    is_bundled=is_bundled,
                    is_valid=False,
                    error_message=(
                        "Java runtime (JRE/JDK) is required. "
                        "Set Java Home or install Android Studio JBR/JDK."
                    ),
                )

        creationflags = 0x08000000 if os.name == "nt" else 0
        env = self.execution_env()

        version_cmds: list[list[str]] = []
        if tool_name in ("adb", "aapt2", "gitleaks"):
            version_cmds = [[str(path), "version"]]
        elif tool_name == "git":
            version_cmds = [[str(path), "--version"]]
        elif tool_name == "scrcpy":
            version_cmds = [[str(path), "--version"], [str(path), "-v"]]
        elif tool_name == "apksigner":
            version_cmds = [[str(path), "--version"], [str(path), "version"]]
        elif tool_name == "bundletool":
            if path.suffix.lower() == ".jar":
                jh = self.find_java_home()
                java_bin = (
                    str(jh / "bin" / ("java.exe" if os.name == "nt" else "java"))
                    if jh
                    else "java"
                )
                version_cmds = [[java_bin, "-jar", str(path), "version"]]
            else:
                version_cmds = [[str(path), "version"]]
        elif tool_name == "apkanalyzer":
            version_cmds = [[str(path), "--version"]]

        version_str: str | None = None
        error_msg: str | None = None

        for cmd in version_cmds:
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    creationflags=creationflags,
                    env=env,
                )
                output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
                output = output.strip()
                if proc.returncode == 0 or (
                    tool_name == "apkanalyzer" and "apkanalyzer" in output.lower()
                ):
                    version_str = self._parse_version(tool_name, output)
                    break
                else:
                    error_msg = (
                        proc.stderr.strip()
                        or proc.stdout.strip()
                        or f"Process exited with code {proc.returncode}"
                    )
            except subprocess.TimeoutExpired:
                error_msg = "Version check timed out after 5 seconds"
            except Exception as exc:
                error_msg = str(exc)

        if version_str is not None:
            return ToolInfo(
                name=tool_name,
                path=path,
                version=version_str,
                is_bundled=is_bundled,
                is_valid=True,
                error_message=None,
            )

        if java_dependent and path.is_file():
            return ToolInfo(
                name=tool_name,
                path=path,
                version="Available (Java ready)",
                is_bundled=is_bundled,
                is_valid=True,
                error_message=None,
            )

        return ToolInfo(
            name=tool_name,
            path=path,
            version=None,
            is_bundled=is_bundled,
            is_valid=False,
            error_message=error_msg or "Failed to verify tool version",
        )

    def verify_all(self) -> dict[str, ToolInfo]:
        """Verify all known tools actively."""
        return {tool_name: self.verify_tool(tool_name) for tool_name in _KNOWN_TOOLS}

    def _parse_version(self, tool_name: str, output: str) -> str:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if not lines:
            return "Available"

        if tool_name == "adb":
            match = re.search(r"Android Debug Bridge version\s+([0-9.]+)", output)
            if match:
                build_match = re.search(r"Version\s+([0-9.\-_a-zA-Z]+)", output)
                if build_match:
                    return f"{match.group(1)} ({build_match.group(1)})"
                return match.group(1)
        elif tool_name == "aapt2":
            match = re.search(
                r"(?:aapt\)?\s*|version\s+)([0-9.:\-_a-zA-Z]+)", output, re.IGNORECASE
            )
            if match:
                return match.group(1)
        elif tool_name == "gitleaks":
            match = re.search(r"v?([0-9]+\.[0-9]+\.[0-9]+)", output)
            if match:
                return match.group(1)
        elif tool_name == "git":
            match = re.search(r"git version\s+([^\s]+)", output)
            if match:
                return match.group(1)
        elif tool_name == "scrcpy":
            match = re.search(r"scrcpy\s+([0-9.]+)", output)
            if match:
                return match.group(1)
        elif tool_name in ("apksigner", "bundletool"):
            match = re.search(r"([0-9]+\.[0-9]+(?:\.[0-9]+)?)", output)
            if match:
                return match.group(1)
        elif tool_name == "apkanalyzer":
            match = re.search(r"version\s+([0-9.]+)", output, re.IGNORECASE)
            if match:
                return match.group(1)
            return "Detected"

        first_line = lines[0]
        if len(first_line) > 40:
            first_line = first_line[:37] + "..."
        return first_line

    def _from_bundled(self, tool_name: str) -> Path | None:
        import sys

        exe = f"{tool_name}.exe" if os.name == "nt" else tool_name
        pkg_root = Path(__file__).resolve().parent.parent
        candidates = [
            pkg_root / "resources" / "bin" / exe,
            Path(sys.executable).parent / "resources" / "bin" / exe,
            Path(sys.executable).parent / "droiddesk" / "resources" / "bin" / exe,
            Path(sys.executable).parent / exe,
        ]
        for cand in candidates:
            if cand.is_file():
                return cand
        return None

    def _from_settings(self, tool_name: str) -> Path | None:
        attr = f"{tool_name}_path"
        val: Path | None = getattr(self._settings, attr, None)
        if val is not None and val.is_file():
            return val
        return None

    def _from_configured_sdk(self, tool_name: str) -> Path | None:
        if self._settings.android_sdk_path and self._settings.android_sdk_path.is_dir():
            return self._search_sdk_root(self._settings.android_sdk_path, tool_name)
        return None

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
                candidates.append(sub / "bin" / f"{tool_name}.exe")

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

        if self._settings.java_home_path:
            cand = self._settings.java_home_path
            if (cand / "bin" / exe_name).is_file():
                return cand
            if (cand / exe_name).is_file():
                return cand.parent

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

        which_java = shutil.which("java")
        if which_java:
            jpath = Path(which_java).resolve()
            if jpath.parent.name == "bin" and (jpath.parent / exe_name).is_file():
                return jpath.parent.parent

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
