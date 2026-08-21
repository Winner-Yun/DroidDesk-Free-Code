"""EnvService — Section 6.8. Reads .droiddesk/environments.toml, switches the
active environment (copying env/Firebase files into place after backing up what
was there), and publishes the active environment so it can be shown persistently
in the status bar, coloured by risk. That always-visible state is what prevents
most of the mistakes the tool exists to catch.
"""

from __future__ import annotations

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

    def switch_to(self, environment: Environment) -> None:
        # TODO(Phase 5): back up files currently in place, copy env_file and
        # firebase config into position, then set self._active and emit
        # active_environment_changed.
        raise NotImplementedError
