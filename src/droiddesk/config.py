"""Settings model, per-user paths, and persisted configuration.

Config lives under %APPDATA%\\DroidDesk; the SQLite database and cache live under
%LOCALAPPDATA%\\DroidDesk — never under Program Files, which is not user-writable.
See Section 10.2 of the spec.
"""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_path, user_data_path
from pydantic import BaseModel


class Settings(BaseModel):
    adb_path: Path | None = None
    aapt2_path: Path | None = None
    apksigner_path: Path | None = None
    apkanalyzer_path: Path | None = None
    bundletool_path: Path | None = None
    gitleaks_path: Path | None = None
    scrcpy_path: Path | None = None
    git_path: Path | None = None

    config_dir: Path = user_config_path("DroidDesk", appauthor=False)
    data_dir: Path = user_data_path("DroidDesk", appauthor=False)

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "droiddesk.db"

    @classmethod
    def load(cls) -> "Settings":
        # TODO(Phase 1): read config.toml if present, falling back to defaults.
        settings = cls()
        settings.config_dir.mkdir(parents=True, exist_ok=True)
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        return settings

    def save(self) -> None:
        # TODO(Phase 1): serialize to config_file as TOML.
        raise NotImplementedError
