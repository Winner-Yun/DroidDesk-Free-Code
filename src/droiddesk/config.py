"""Settings model, per-user paths, and persisted configuration.

Config lives under %APPDATA%\\DroidDesk; the SQLite database and cache live under
%LOCALAPPDATA%\\DroidDesk - never under Program Files, which is not user-writable.
See Section 10.2 of the spec.
"""

from __future__ import annotations

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
        settings.config_dir.mkdir(parents=True, exist_ok=True)
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        if settings.config_file.is_file():
            with settings.config_file.open("rb") as fh:
                data = tomllib.load(fh)
            for field in _PATH_FIELDS:
                if field in data:
                    setattr(settings, field, Path(data[field]))
            if "active_apk_hash" in data:
                settings.active_apk_hash = str(data["active_apk_hash"])
        return settings

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        lines = []
        for field in _PATH_FIELDS:
            value: Path | None = getattr(self, field)
            if value is not None:
                escaped = str(value).replace("\\", "\\\\")
                lines.append(f'{field} = "{escaped}"')
        if self.active_apk_hash is not None:
            escaped_hash = self.active_apk_hash.replace('"', '\\"')
            lines.append(f'active_apk_hash = "{escaped_hash}"')
        self.config_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
