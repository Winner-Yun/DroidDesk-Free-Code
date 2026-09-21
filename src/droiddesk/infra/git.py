"""GitClient: wrapper around git commands using ProcessRunner."""

from __future__ import annotations

from pathlib import Path

from droiddesk.infra.process import ProcessRunner
from droiddesk.infra.tools import ToolLocator


class GitClient:
    """Lightweight Git wrapper for working-tree status and branch discovery."""

    def __init__(
        self,
        runner: ProcessRunner | None = None,
        tool_locator: ToolLocator | None = None,
    ) -> None:
        self._runner = runner or ProcessRunner()
        self._tools = tool_locator

    def _git_path(self) -> Path:
        if self._tools:
            try:
                return self._tools.resolve("git")
            except Exception:
                pass
        return Path("git")

    def is_clean(self, project_root: Path) -> bool:
        """Return True if working tree has no uncommitted/staged/untracked changes."""
        try:
            res = self._runner.run(
                self._git_path(),
                ["status", "--porcelain"],
                cwd=project_root,
                timeout=15.0,
            )
            if res.exit_code != 0:
                return False
            return len(res.stdout.strip()) == 0
        except Exception:
            return False

    def current_branch(self, project_root: Path) -> str | None:
        """Return current branch name, or None if git fails."""
        try:
            res = self._runner.run(
                self._git_path(),
                ["rev-parse", "--abbrev-ref", "HEAD"],
                cwd=project_root,
                timeout=10.0,
            )
            if res.exit_code != 0:
                return None
            branch = res.stdout.strip()
            return branch if branch else None
        except Exception:
            return None
