"""Settings model, user paths, and persisted configuration."""

from __future__ import annotations

import contextlib
import tomllib
from pathlib import Path

from platformdirs import user_config_path, user_data_path
from pydantic import BaseModel

_PATH_FIELDS = (
    "adb_path",
    "aapt2_path",
    "apksigner_path",
    "apkanalyzer_path",
    "bundletool_path",
    "gitleaks_path",
    "scrcpy_path",
    "git_path",
    "emulator_path",
    "avdmanager_path",
    "sdkmanager_path",
    "android_sdk_path",
    "java_home_path",
    "reports_output_dir",
    "default_organizer_rules",
)


class Settings(BaseModel):
    adb_path: Path | None = None
    aapt2_path: Path | None = None
    apksigner_path: Path | None = None
    apkanalyzer_path: Path | None = None
    bundletool_path: Path | None = None
    gitleaks_path: Path | None = None
    scrcpy_path: Path | None = None
    git_path: Path | None = None
    emulator_path: Path | None = None
    avdmanager_path: Path | None = None
    sdkmanager_path: Path | None = None
    android_sdk_path: Path | None = None
    java_home_path: Path | None = None
    reports_output_dir: Path | None = None
    default_organizer_rules: Path | None = None
    device_poll_interval_s: int = 2
    theme_mode: str = "dark"
    active_apk_hash: str | None = None

    config_dir: Path = user_config_path("DroidDesk", appauthor=False)
    data_dir: Path = user_data_path("DroidDesk", appauthor=False)

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "droiddesk.db"

    @classmethod
    def load(cls) -> Settings:
        settings = cls()
        with contextlib.suppress(OSError):
            settings.config_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            settings.data_dir.mkdir(parents=True, exist_ok=True)
        if settings.config_file.is_file():
            try:
                with settings.config_file.open("rb") as fh:
                    data = tomllib.load(fh)
                for field in _PATH_FIELDS:
                    if field in data and data[field]:
                        setattr(settings, field, Path(str(data[field])))
                if "active_apk_hash" in data and data["active_apk_hash"] is not None:
                    settings.active_apk_hash = str(data["active_apk_hash"])
                if "device_poll_interval_s" in data and data["device_poll_interval_s"] is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        settings.device_poll_interval_s = int(data["device_poll_interval_s"])
                if "theme_mode" in data and data["theme_mode"] is not None:
                    settings.theme_mode = str(data["theme_mode"])
            except Exception:
                pass
        return settings

    def save(self) -> None:
        with contextlib.suppress(OSError):
            self.config_dir.mkdir(parents=True, exist_ok=True)
        lines = []
        for field in _PATH_FIELDS:
            value: Path | None = getattr(self, field, None)
            if value is not None:
                escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{field} = "{escaped}"')
        if self.active_apk_hash is not None:
            escaped_hash = self.active_apk_hash.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'active_apk_hash = "{escaped_hash}"')
        lines.append(f"device_poll_interval_s = {self.device_poll_interval_s}")
        escaped_theme = self.theme_mode.replace('"', '\\"')
        lines.append(f'theme_mode = "{escaped_theme}"')
        self.config_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
