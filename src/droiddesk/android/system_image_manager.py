"""System Image Manager: discovers, parses, and downloads Android system images."""

from __future__ import annotations

import os
import re
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, QThread, Signal

from droiddesk.android.command_runner import CommandRunner
from droiddesk.android.models import SystemImage
from droiddesk.infra.tools import ToolLocator

_API_LEVEL_TO_VERSION: dict[int, str] = {
    36: "16.0 (Baklava)",
    35: "15.0 (Vanilla Ice Cream)",
    34: "14.0 (Upside Down Cake)",
    33: "13.0 (Tiramisu)",
    32: "12L (Sv2)",
    31: "12.0 (Snow Cone)",
    30: "11.0 (Red Velvet Cake)",
    29: "10.0 (Quince Tart)",
    28: "9.0 (Pie)",
    27: "8.1 (Oreo MR1)",
    26: "8.0 (Oreo)",
    25: "7.1 (Nougat MR1)",
    24: "7.0 (Nougat)",
}

# Standard system image packages available via Android SDK
_POPULAR_SYSTEM_IMAGES: list[dict[str, str | int]] = [
    {
        "api": 35,
        "version": "15.0",
        "tag": "google_apis_playstore",
        "abi": "x86_64",
        "path": "system-images;android-35;google_apis_playstore;x86_64",
    },
    {
        "api": 35,
        "version": "15.0",
        "tag": "google_apis",
        "abi": "x86_64",
        "path": "system-images;android-35;google_apis;x86_64",
    },
    {
        "api": 34,
        "version": "14.0",
        "tag": "google_apis_playstore",
        "abi": "x86_64",
        "path": "system-images;android-34;google_apis_playstore;x86_64",
    },
    {
        "api": 34,
        "version": "14.0",
        "tag": "google_apis",
        "abi": "x86_64",
        "path": "system-images;android-34;google_apis;x86_64",
    },
    {
        "api": 33,
        "version": "13.0",
        "tag": "google_apis_playstore",
        "abi": "x86_64",
        "path": "system-images;android-33;google_apis_playstore;x86_64",
    },
    {
        "api": 33,
        "version": "13.0",
        "tag": "google_apis",
        "abi": "x86_64",
        "path": "system-images;android-33;google_apis;x86_64",
    },
    {
        "api": 31,
        "version": "12.0",
        "tag": "google_apis",
        "abi": "x86_64",
        "path": "system-images;android-31;google_apis;x86_64",
    },
    {
        "api": 30,
        "version": "11.0",
        "tag": "google_apis",
        "abi": "x86_64",
        "path": "system-images;android-30;google_apis;x86_64",
    },
    {
        "api": 29,
        "version": "10.0",
        "tag": "google_apis",
        "abi": "x86_64",
        "path": "system-images;android-29;google_apis;x86_64",
    },
]


class ImageDownloadThread(QThread):
    progress = Signal(str)  # Progress message / percentage
    finished_success = Signal(str)  # Package path
    failed = Signal(str)  # Error message

    def __init__(
        self,
        sdkmanager_path: Path,
        package_path: str,
        runner: CommandRunner,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._sdkmanager_path = sdkmanager_path
        self._package_path = package_path
        self._runner = runner

    def run(self) -> None:
        try:
            self.progress.emit(f"Preparing to install {self._package_path}...")
            # We automatically accept license by piping 'y' into sdkmanager
            res = self._runner.run(
                self._sdkmanager_path,
                ["--install", self._package_path],
                timeout=600.0,
                input_text="y\ny\ny\ny\n",
            )
            if res.exit_code == 0:
                self.finished_success.emit(self._package_path)
            else:
                err = (
                    res.stderr.strip() or res.stdout.strip() or f"Exited with code {res.exit_code}"
                )
                self.failed.emit(f"Download failed: {err}")
        except Exception as exc:
            self.failed.emit(f"Download error: {exc}")


class SystemImageManager:
    """Manages discovering installed system images and orchestrating downloads."""

    def __init__(self, tool_locator: ToolLocator, runner: CommandRunner | None = None) -> None:
        self._tool_locator = tool_locator
        self._runner = runner or CommandRunner(tool_locator)

    def list_installed_images(self) -> list[SystemImage]:
        """Scan SDK system-images directories on disk and return parsed SystemImage list."""
        sdk_candidates = self._find_sdk_roots()
        results: list[SystemImage] = []
        seen_paths: set[str] = set()

        for sdk_root in sdk_candidates:
            si_dir = sdk_root / "system-images"
            if not si_dir.is_dir():
                continue

            # Directory layout: system-images/android-XX/tag/abi
            try:
                for api_dir in si_dir.iterdir():
                    if not api_dir.is_dir():
                        continue
                    m_api = re.search(r"android-(\d+)", api_dir.name)
                    if not m_api:
                        continue
                    api_level = int(m_api.group(1))
                    ver_name = _API_LEVEL_TO_VERSION.get(api_level, f"Android API {api_level}")

                    for tag_dir in api_dir.iterdir():
                        if not tag_dir.is_dir():
                            continue
                        tag = tag_dir.name

                        for abi_dir in tag_dir.iterdir():
                            if not abi_dir.is_dir():
                                continue
                            abi = abi_dir.name

                            pkg_path = f"system-images;{api_dir.name};{tag};{abi}"
                            if pkg_path in seen_paths:
                                continue

                            # Verify package.xml or system.img
                            if (abi_dir / "package.xml").is_file() or (
                                abi_dir / "system.img"
                            ).is_file():
                                seen_paths.add(pkg_path)
                                results.append(
                                    SystemImage(
                                        path=pkg_path,
                                        api_level=api_level,
                                        android_version=ver_name,
                                        tag=tag,
                                        abi=abi,
                                        is_installed=True,
                                        location=abi_dir,
                                    )
                                )
            except Exception as exc:
                logger.warning(f"Error scanning system images in {si_dir}: {exc}")

        # Sort descending by API level
        results.sort(key=lambda img: (img.api_level, img.tag, img.abi), reverse=True)
        return results

    def list_all_available_images(self) -> list[SystemImage]:
        """Return combined list of installed and well-known downloadable system images."""
        installed = self.list_installed_images()
        installed_keys = {img.path for img in installed}

        all_images: list[SystemImage] = list(installed)

        for item in _POPULAR_SYSTEM_IMAGES:
            pkg_path = str(item["path"])
            if pkg_path not in installed_keys:
                api_lvl = int(item["api"])
                ver = _API_LEVEL_TO_VERSION.get(api_lvl, f"Android API {api_lvl}")
                all_images.append(
                    SystemImage(
                        path=pkg_path,
                        api_level=api_lvl,
                        android_version=ver,
                        tag=str(item["tag"]),
                        abi=str(item["abi"]),
                        is_installed=False,
                    )
                )

        all_images.sort(key=lambda img: (img.is_installed, img.api_level), reverse=True)
        return all_images

    def create_download_thread(
        self, package_path: str, parent: QObject | None = None
    ) -> ImageDownloadThread:
        """Create a worker thread to download a system image using sdkmanager."""
        sdkmanager_path = self._tool_locator.resolve("sdkmanager")
        return ImageDownloadThread(
            sdkmanager_path=sdkmanager_path,
            package_path=package_path,
            runner=self._runner,
            parent=parent,
        )

    def _find_sdk_roots(self) -> list[Path]:
        candidates: list[Path] = []
        if (
            self._tool_locator._settings.android_sdk_path
            and self._tool_locator._settings.android_sdk_path.is_dir()
        ):
            candidates.append(self._tool_locator._settings.android_sdk_path)

        for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            val = os.environ.get(env_var)
            if val and Path(val).is_dir():
                candidates.append(Path(val))

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Android" / "Sdk")

        candidates.extend(
            [
                Path(r"C:\Android\Sdk"),
                Path(r"C:\Android\sdk"),
                Path.home() / "AppData" / "Local" / "Android" / "Sdk",
            ]
        )

        seen: set[str] = set()
        unique: list[Path] = []
        for p in candidates:
            res_str = str(p.resolve()) if p.is_dir() else str(p)
            if p.is_dir() and res_str not in seen:
                seen.add(res_str)
                unique.append(p)
        return unique
