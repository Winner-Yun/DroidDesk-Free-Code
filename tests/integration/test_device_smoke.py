"""Requires a real device or a booted emulator. Excluded from the default run
(pyproject.toml: addopts = "-m 'not device'"). Run explicitly with
`pytest -m device`, ideally against a headless emulator per Section 11.
"""

from __future__ import annotations

import pytest


@pytest.mark.device
def test_adb_client_lists_connected_devices() -> None:
    # TODO(Phase 1): construct a real AdbClient and assert at least one device
    # is returned when a device/emulator is attached.
    pytest.skip("Phase 1: implement once AdbClient.list_devices lands")
