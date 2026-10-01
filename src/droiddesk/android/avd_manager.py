"""AVD (Android Virtual Device) Manager.

Manages creation, listing, configuration, and deletion of AVDs.
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
from pathlib import Path

from loguru import logger

from droiddesk.android.command_runner import CommandRunner
from droiddesk.android.models import AvdInfo, DeviceProfile
from droiddesk.infra.tools import ToolLocator

_WELL_KNOWN_DEVICE_PROFILES: list[DeviceProfile] = [
    DeviceProfile(
        id="pixel_8", name="Pixel 8", oem="Google", screen_size='6.2"', resolution="1080x2400"
    ),
    DeviceProfile(
        id="pixel_7", name="Pixel 7", oem="Google", screen_size='6.3"', resolution="1080x2400"
    ),
    DeviceProfile(
        id="pixel_6", name="Pixel 6", oem="Google", screen_size='6.4"', resolution="1080x2400"
    ),
    DeviceProfile(
        id="pixel_8_pro",
        name="Pixel 8 Pro",
        oem="Google",
        screen_size='6.7"',
        resolution="1344x2992",
    ),
    DeviceProfile(
        id="pixel_7_pro",
        name="Pixel 7 Pro",
        oem="Google",
        screen_size='6.7"',
        resolution="1440x3120",
    ),
    DeviceProfile(
        id="pixel_fold", name="Pixel Fold", oem="Google", screen_size='7.6"', resolution="1840x2208"
    ),
    DeviceProfile(
        id="pixel_tablet",
        name="Pixel Tablet",
        oem="Google",
        screen_size='10.95"',
        resolution="2560x1600",
    ),
    DeviceProfile(
        id="Medium Phone",
        name="Medium Phone",
        oem="Generic",
        screen_size='6.0"',
        resolution="1080x2400",
    ),
    DeviceProfile(
        id="7in WSVGA (Tablet)",
        name='7" WSVGA Tablet',
        oem="Generic",
        screen_size='7.0"',
        resolution="1024x600",
    ),
    DeviceProfile(
        id="10.1in WXGA (Tablet)",
        name='10.1" Tablet',
        oem="Generic",
        screen_size='10.1"',
        resolution="1280x800",
    ),
]


class AvdManager:
    """Manages virtual device configurations and calls official avdmanager SDK tool."""

    def __init__(self, tool_locator: ToolLocator, runner: CommandRunner | None = None) -> None:
        self._tool_locator = tool_locator
        self._runner = runner or CommandRunner(tool_locator)

    @property
    def avd_root_dir(self) -> Path:
        """Default directory where Android virtual devices reside."""
        return Path.home() / ".android" / "avd"

    def list_avds(self) -> list[AvdInfo]:
        """List all Android Virtual Devices defined on the system."""
        avds: list[AvdInfo] = []
        parsed_names: set[str] = set()

        # Method 1: Query avdmanager list avd if available
        try:
            avdmanager_path = self._tool_locator.resolve("avdmanager")
            res = self._runner.run(avdmanager_path, ["list", "avd"], timeout=15.0)
            if res.exit_code == 0:
                avds = self._parse_avdmanager_list_avd(res.stdout)
                parsed_names = {a.name for a in avds}
        except Exception as exc:
            logger.warning(f"Error querying avdmanager list avd: {exc}")

        # Method 2: Inspect ~/.android/avd/*.ini to detect any additional AVDs or enrich configs
        if self.avd_root_dir.is_dir():
            try:
                for ini_path in self.avd_root_dir.glob("*.ini"):
                    avd_name = ini_path.stem
                    config_ini_path = self.avd_root_dir / f"{avd_name}.avd" / "config.ini"
                    config_dict = (
                        self._parse_ini_file(config_ini_path) if config_ini_path.is_file() else {}
                    )

                    # If already parsed from avdmanager, enrich config
                    existing = next((a for a in avds if a.name == avd_name), None)
                    if existing:
                        existing.config.update(config_dict)
                        if not existing.display_name and "avd.ini.displayname" in config_dict:
                            existing.display_name = config_dict["avd.ini.displayname"]
                        if not existing.abi and "abi.type" in config_dict:
                            existing.abi = config_dict["abi.type"]
                    elif avd_name not in parsed_names:
                        display = config_dict.get("avd.ini.displayname", avd_name.replace("_", " "))
                        avds.append(
                            AvdInfo(
                                name=avd_name,
                                display_name=display,
                                device_name=config_dict.get("hw.device.name"),
                                path=self.avd_root_dir / f"{avd_name}.avd",
                                target=config_dict.get("target"),
                                abi=config_dict.get("abi.type"),
                                skin=config_dict.get("skin.name"),
                                sdcard=config_dict.get("sdcard.size"),
                                config=config_dict,
                            )
                        )
            except Exception as exc:
                logger.warning(f"Error inspecting AVD directory {self.avd_root_dir}: {exc}")

        return avds

    def get_avd(self, name: str) -> AvdInfo | None:
        """Find an AVD by its unique name."""
        return next((a for a in self.list_avds() if a.name == name), None)

    def get_avd_path(self, name: str) -> Path | None:
        """Resolve directory path for a given AVD name."""
        avd = self.get_avd(name)
        if avd and avd.path and avd.path.exists():
            return avd.path
        candidate1 = self.avd_root_dir / f"{name}.avd"
        if candidate1.exists():
            return candidate1
        candidate2 = Path.home() / ".android" / "avd" / f"{name}.avd"
        if candidate2.exists():
            return candidate2
        return None

    def list_device_profiles(self) -> list[DeviceProfile]:
        """Fetch available hardware device profiles via avdmanager list device."""
        profiles: list[DeviceProfile] = []
        try:
            avdmanager_path = self._tool_locator.resolve("avdmanager")
            res = self._runner.run(avdmanager_path, ["list", "device"], timeout=20.0)
            if res.exit_code == 0:
                profiles = self._parse_device_profiles(res.stdout)
        except Exception as exc:
            logger.warning(f"Error fetching device profiles from avdmanager: {exc}")

        if not profiles:
            return list(_WELL_KNOWN_DEVICE_PROFILES)

        # Merge well-known profiles if any are missing
        existing_ids = {p.id.lower() for p in profiles}
        for fallback in _WELL_KNOWN_DEVICE_PROFILES:
            if fallback.id.lower() not in existing_ids:
                profiles.append(fallback)

        return profiles

    def create_avd(
        self,
        name: str,
        system_image_path: str,
        device_profile_id: str | None = None,
        ram_mb: int | None = None,
        sdcard_size_mb: int | None = None,
        storage_mb: int | None = None,
    ) -> tuple[bool, str]:
        """Create a new Android Virtual Device using avdmanager."""
        clean_name = re.sub(r"[^\w\-_.]", "_", name.strip())
        if not clean_name:
            return False, "AVD name cannot be empty or contain only special characters."

        try:
            avdmanager_path = self._tool_locator.resolve("avdmanager")
        except Exception as exc:
            return False, f"AVD Manager tool is unavailable: {exc}"

        args = ["create", "avd", "-n", clean_name, "-k", system_image_path, "--force"]
        if device_profile_id:
            args.extend(["-d", device_profile_id])
        if sdcard_size_mb:
            args.extend(["-c", f"{sdcard_size_mb}M"])

        logger.info(f"Creating AVD '{clean_name}' with image '{system_image_path}'...")
        try:
            # We respond "no" to the prompt "Do you wish to create a custom hardware profile? [no]"
            res = self._runner.run(avdmanager_path, args, timeout=60.0, input_text="no\n")
            if res.exit_code != 0:
                err = res.stderr.strip() or res.stdout.strip()
                return False, f"Failed to create AVD: {err}"

            # Post-creation: adjust config.ini for custom RAM / storage if requested
            self._update_avd_config(clean_name, ram_mb=ram_mb, storage_mb=storage_mb)
            return True, f"AVD '{clean_name}' created successfully."
        except Exception as exc:
            return False, f"AVD creation error: {exc}"

    def delete_avd(self, name: str) -> tuple[bool, str]:
        """Delete an existing AVD definition. Keeps system images intact."""
        clean_name = name.strip()
        if not clean_name:
            return False, "AVD name cannot be empty."

        deleted_by_cli = False
        error_msg = ""

        # Strategy 1: Official avdmanager delete avd -n <name>
        try:
            avdmanager_path = self._tool_locator.resolve("avdmanager")
            res = self._runner.run(
                avdmanager_path, ["delete", "avd", "-n", clean_name], timeout=30.0
            )
            if res.exit_code == 0:
                logger.info(f"AVD '{clean_name}' deleted successfully via avdmanager.")
                deleted_by_cli = True
            else:
                error_msg = res.stderr.strip() or res.stdout.strip()
                logger.warning(
                    f"avdmanager delete avd returned {res.exit_code}: {error_msg}"
                )
        except Exception as exc:
            error_msg = str(exc)
            logger.warning(f"Error running avdmanager delete avd: {exc}")

        # Strategy 2: File-level cleanup / fallback for ~/.android/avd/<name>.ini and <name>.avd
        # If CLI failed or left leftover files, safely purge only the specific virtual device files.
        ini_file = self.avd_root_dir / f"{clean_name}.ini"
        avd_folder = self.avd_root_dir / f"{clean_name}.avd"

        # Check if the .ini specified a custom folder path
        custom_folder: Path | None = None
        if ini_file.is_file():
            try:
                for line in ini_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("path="):
                        p = Path(line.split("=", 1)[1].strip())
                        if p.exists() and p.name.endswith(".avd"):
                            custom_folder = p
            except Exception:
                pass

        files_were_removed = False
        try:
            if ini_file.exists():
                ini_file.unlink(missing_ok=True)
                files_were_removed = True

            target_folders = [
                f
                for f in (avd_folder, custom_folder)
                if f and f.is_dir() and f.name.endswith(".avd")
            ]
            for folder in target_folders:
                for root, dirs, files in os.walk(folder, topdown=False):
                    for f in files:
                        fp = os.path.join(root, f)
                        with contextlib.suppress(Exception):
                            os.chmod(fp, stat.S_IWRITE)
                            os.remove(fp)
                    for d in dirs:
                        dp = os.path.join(root, d)
                        with contextlib.suppress(Exception):
                            os.rmdir(dp)
                with contextlib.suppress(Exception):
                    folder.rmdir()
                    files_were_removed = True
        except Exception as exc:
            logger.warning(f"Error purging AVD files for '{clean_name}': {exc}")
            if not deleted_by_cli and not files_were_removed:
                return False, f"Could not delete emulator: {exc} ({error_msg})"

        if deleted_by_cli or files_were_removed:
            logger.info(f"AVD '{clean_name}' completely removed.")
            return True, f"Emulator '{clean_name}' removed successfully."

        return False, f"Could not delete emulator: {error_msg or 'Device not found.'}"

    def _update_avd_config(
        self,
        name: str,
        ram_mb: int | None = None,
        storage_mb: int | None = None,
    ) -> None:
        """Write custom hardware properties to config.ini."""
        config_path = self.avd_root_dir / f"{name}.avd" / "config.ini"
        if not config_path.is_file():
            return

        try:
            lines = config_path.read_text(encoding="utf-8").splitlines()
            new_lines: list[str] = []
            modified_ram = False
            modified_storage = False

            for line in lines:
                if ram_mb and line.startswith("hw.ramSize"):
                    new_lines.append(f"hw.ramSize = {ram_mb}")
                    modified_ram = True
                elif storage_mb and line.startswith("disk.dataPartition.size"):
                    new_lines.append(f"disk.dataPartition.size = {storage_mb}M")
                    modified_storage = True
                else:
                    new_lines.append(line)

            if ram_mb and not modified_ram:
                new_lines.append(f"hw.ramSize = {ram_mb}")
            if storage_mb and not modified_storage:
                new_lines.append(f"disk.dataPartition.size = {storage_mb}M")

            config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Could not update config.ini for AVD '{name}': {exc}")

    def _parse_avdmanager_list_avd(self, output: str) -> list[AvdInfo]:
        """Parse avdmanager list avd output into AvdInfo objects."""
        avds: list[AvdInfo] = []
        blocks = re.split(r"-{4,}", output)

        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue

            name: str | None = None
            device_name: str | None = None
            path: Path | None = None
            target: str | None = None
            based_on: str | None = None
            abi: str | None = None
            skin: str | None = None
            sdcard: str | None = None
            error: str | None = None

            for line in lines:
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Device:"):
                    device_name = line.split(":", 1)[1].strip()
                elif line.startswith("Path:"):
                    path = Path(line.split(":", 1)[1].strip())
                elif line.startswith("Target:"):
                    target = line.split(":", 1)[1].strip()
                elif "Based on:" in line:
                    based_on = line.split("Based on:", 1)[1].strip()
                    m_abi = re.search(r"Tag/ABI:\s*([^ \t\r\n]+)", line)
                    if m_abi:
                        abi = m_abi.group(1)
                elif line.startswith("Skin:"):
                    skin = line.split(":", 1)[1].strip()
                elif line.startswith("Sdcard:"):
                    sdcard = line.split(":", 1)[1].strip()
                elif line.startswith("Error:"):
                    error = line.split(":", 1)[1].strip()

            if name:
                display = name.replace("_", " ")
                avds.append(
                    AvdInfo(
                        name=name,
                        display_name=display,
                        device_name=device_name,
                        path=path,
                        target=target,
                        based_on=based_on,
                        abi=abi,
                        skin=skin,
                        sdcard=sdcard,
                        error=error,
                    )
                )

        return avds

    def _parse_device_profiles(self, output: str) -> list[DeviceProfile]:
        """Parse avdmanager list device output into DeviceProfile objects."""
        profiles: list[DeviceProfile] = []
        blocks = re.split(r"-{4,}", output)

        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue

            dev_id: str | None = None
            name: str | None = None
            oem: str = "Google"
            tag: str | None = None

            for line in lines:
                m_id = re.search(r'id:\s*\d+\s+or\s+"([^"]+)"', line)
                if m_id:
                    dev_id = m_id.group(1)
                elif line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("OEM :"):
                    oem = line.split(":", 1)[1].strip()
                elif line.startswith("Tag :"):
                    tag = line.split(":", 1)[1].strip()

            if dev_id and name:
                profiles.append(
                    DeviceProfile(
                        id=dev_id,
                        name=name,
                        oem=oem,
                        tag=tag,
                    )
                )

        return profiles

    def _parse_ini_file(self, file_path: Path) -> dict[str, str]:
        config: dict[str, str] = {}
        try:
            for line in file_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    config[key.strip()] = val.strip()
        except Exception:
            pass
        return config
