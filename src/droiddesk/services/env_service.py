"""EnvService - Section 6.8. Reads .droiddesk/environments.toml, switches the
active environment (copying env/Firebase files into place after backing up what
was there), and publishes the active environment so it can be shown persistently
in the status bar, coloured by risk. That always-visible state is what prevents
most of the mistakes the tool exists to catch.
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from droiddesk.core.profiles import Environment

_ENVIRONMENTS_FILE = ".droiddesk/environments.toml"


class EnvService(QObject):
    active_environment_changed = Signal(object)  # Environment | None

    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self._project_root = project_root
        self._active: Environment | None = None

    @property
    def project_root(self) -> Path:
        return self._project_root

    def load_environments(self) -> list[Environment]:
        path = self._project_root / _ENVIRONMENTS_FILE
        if not path.is_file():
            return []
        with path.open("rb") as f:
            data = tomllib.load(f)
        return [
            Environment(key=key, **fields) for key, fields in data.get("environments", {}).items()
        ]

    def active_environment(self) -> Environment | None:
        return self._active

    def set_active_environment(self, environment: Environment | None) -> None:
        """Set active environment without copying files (e.g., during app startup)."""
        self._active = environment
        self.active_environment_changed.emit(environment)

    def save_environments(self, environments: list[Environment]) -> None:
        """Persist environments list directly to .droiddesk/environments.toml."""
        path = self._project_root / _ENVIRONMENTS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# DroidDesk Environment Configuration (Section 6.8)",
            "# Managed dynamically by DroidDesk.",
            "",
        ]
        for env in environments:
            lines.append(f"[environments.{env.key}]")
            lines.append(f'label = "{env.label}"')
            lines.append(f'env_file = "{env.env_file}"')
            if env.firebase:
                lines.append(f'firebase = "{env.firebase}"')
            if env.flavor:
                lines.append(f'flavor = "{env.flavor}"')
            if env.api_host:
                lines.append(f'api_host = "{env.api_host}"')
            lines.append(f"allow_release_build = {'true' if env.allow_release_build else 'false'}")
            lines.append(f"require_clean_git = {'true' if env.require_clean_git else 'false'}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")

    def add_or_update_environment(self, environment: Environment) -> None:
        """Add or update an environment and save dynamically."""
        envs = self.load_environments()
        updated = False
        new_list: list[Environment] = []
        for e in envs:
            if e.key == environment.key:
                new_list.append(environment)
                updated = True
            else:
                new_list.append(e)
        if not updated:
            new_list.append(environment)
        self.save_environments(new_list)
        if self._active is None or self._active.key == environment.key:
            self.set_active_environment(environment)

    def delete_environment(self, key: str) -> bool:
        """Delete an environment by its key and update file."""
        envs = self.load_environments()
        filtered = [e for e in envs if e.key != key]
        if len(filtered) == len(envs):
            return False
        self.save_environments(filtered)
        if self._active and self._active.key == key:
            next_active = filtered[0] if filtered else None
            self.set_active_environment(next_active)
        return True

    def discover_project_env_files(self) -> list[str]:
        """Scan project root for actual .env* files dynamically."""
        found: list[str] = []
        if not self._project_root.is_dir():
            return found
        try:
            for item in self._project_root.iterdir():
                if item.is_file() and (
                    item.name.startswith(".env") or item.name.endswith(".env")
                ):
                    found.append(item.name)
        except Exception:
            pass
        return sorted(found)

    def discover_project_firebase_files(self) -> list[str]:
        """Scan project root for actual google-services.json / firebase configs dynamically."""
        found: list[str] = []
        if not self._project_root.is_dir():
            return found
        try:
            for pattern in ["*google-services*.json", "*firebase*.json"]:
                for item in self._project_root.glob(pattern):
                    if item.is_file():
                        found.append(item.relative_to(self._project_root).as_posix())
            app_dir = self._project_root / "app"
            if app_dir.is_dir():
                for item in app_dir.glob("*google-services*.json"):
                    if item.is_file():
                        found.append(item.relative_to(self._project_root).as_posix())
        except Exception:
            pass
        return sorted(list(set(found)))

    def _firebase_destination(self) -> Path:
        app_dir = self._project_root / "app"
        if app_dir.is_dir():
            return app_dir / "google-services.json"
        return self._project_root / "google-services.json"

    def switch_to(self, environment: Environment) -> None:
        """Switch active environment according to Section 6.8.

        Backs up current configurations first, deploys new .env and optional
        Firebase config, and rolls back atomically if a required file is missing
        or an I/O operation fails.
        """
        dest_env = self._project_root / ".env"
        dest_firebase = self._firebase_destination()

        src_env = self._project_root / environment.env_file
        src_firebase = self._project_root / environment.firebase if environment.firebase else None

        # 1. Validation before touching anything
        if not src_env.is_file():
            raise FileNotFoundError(f"Environment source file not found: {src_env}")
        if src_firebase and not src_firebase.is_file():
            raise FileNotFoundError(f"Firebase source file not found: {src_firebase}")

        # 2. Backup current files
        env_backed_up = False
        firebase_backed_up = False
        backup_env = self._project_root / ".env.backup"
        backup_firebase = dest_firebase.parent / f"{dest_firebase.name}.backup"

        try:
            if dest_env.is_file():
                shutil.copyfile(dest_env, backup_env)
                env_backed_up = True

            if dest_firebase.is_file():
                backup_firebase.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dest_firebase, backup_firebase)
                firebase_backed_up = True

            # 3. Copy new files into place
            dest_env.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_env, dest_env)

            if src_firebase:
                dest_firebase.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src_firebase, dest_firebase)

        except Exception as err:
            # Atomic rollback on failure
            if env_backed_up and backup_env.is_file():
                shutil.copyfile(backup_env, dest_env)
            elif dest_env.is_file() and not env_backed_up:
                dest_env.unlink(missing_ok=True)

            if firebase_backed_up and backup_firebase.is_file():
                shutil.copyfile(backup_firebase, dest_firebase)
            elif dest_firebase.is_file() and not firebase_backed_up:
                dest_firebase.unlink(missing_ok=True)

            raise RuntimeError(f"Failed to switch environment: {err}") from err

        # 4. State transition and signal emission
        self._active = environment
        self.active_environment_changed.emit(environment)
