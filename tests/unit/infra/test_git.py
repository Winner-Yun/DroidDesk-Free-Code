from pathlib import Path
from unittest.mock import MagicMock

from droiddesk.infra.git import GitClient
from droiddesk.infra.process import ProcessResult, ProcessRunner


def test_git_client_is_clean_true() -> None:
    runner = MagicMock(spec=ProcessRunner)
    runner.run.return_value = ProcessResult(exit_code=0, stdout="", stderr="")

    client = GitClient(runner=runner)
    assert client.is_clean(Path("C:/dummy")) is True


def test_git_client_is_clean_false_when_dirty() -> None:
    runner = MagicMock(spec=ProcessRunner)
    runner.run.return_value = ProcessResult(
        exit_code=0,
        stdout=" M src/droiddesk/app.py\n?? untracked.txt\n",
        stderr="",
    )

    client = GitClient(runner=runner)
    assert client.is_clean(Path("C:/dummy")) is False


def test_git_client_is_clean_false_on_error() -> None:
    runner = MagicMock(spec=ProcessRunner)
    runner.run.return_value = ProcessResult(
        exit_code=128,
        stdout="",
        stderr="fatal: not a git repository",
    )

    client = GitClient(runner=runner)
    assert client.is_clean(Path("C:/dummy")) is False


def test_git_client_current_branch_success() -> None:
    runner = MagicMock(spec=ProcessRunner)
    runner.run.return_value = ProcessResult(exit_code=0, stdout="main\n", stderr="")

    client = GitClient(runner=runner)
    assert client.current_branch(Path("C:/dummy")) == "main"


def test_git_client_current_branch_error() -> None:
    runner = MagicMock(spec=ProcessRunner)
    runner.run.return_value = ProcessResult(
        exit_code=128,
        stdout="",
        stderr="fatal: not a git repository",
    )

    client = GitClient(runner=runner)
    assert client.current_branch(Path("C:/dummy")) is None
