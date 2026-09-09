"""Shared fixtures. Device-requiring tests use @pytest.mark.device and are excluded
from the default run (see pyproject.toml addopts and Section 11).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    (tmp_path / ".droiddesk").mkdir()
    return tmp_path


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]
