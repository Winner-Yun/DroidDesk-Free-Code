"""Exception hierarchy shared across layers.

Every feature that depends on an external binary must check availability first and
raise ToolNotFoundError rather than letting a raw FileNotFoundError traceback reach
the user. See Section 3.1.
"""

from __future__ import annotations


class DroidDeskError(Exception):
    """Base class for all DroidDesk-raised errors."""


class ToolNotFoundError(DroidDeskError):
    """An external tool (adb, aapt2, gitleaks, ...) could not be resolved."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(f"Required tool not found: {tool_name}")
        self.tool_name = tool_name


class ProcessTimeoutError(DroidDeskError):
    """A one-shot subprocess call exceeded its timeout."""


class DeviceUnauthorizedError(DroidDeskError):
    """Device is connected but has not accepted the RSA debugging key."""


class DeviceOfflineError(DroidDeskError):
    """Device shows as offline, usually a stalled USB connection."""


class ApkParseError(DroidDeskError):
    """androguard / pyaxmlparser could not parse the given APK."""


class UnexpectedToolOutputError(DroidDeskError):
    """Parsed output from an external tool did not match the expected format.

    Raised instead of silently returning wrong data when a tool's output format
    drifts after an SDK update. See Section 12, "External tool versions drift".
    """


class MigrationError(DroidDeskError):
    """A SQLite schema migration failed to apply."""
