"""User-editable structured data: test profiles, environments, command guards.

Pydantic, per Section 2.1 - these are edited by the user (directly as TOML, or via a
form), so schema validation with readable errors matters more here than elsewhere.
"""

from __future__ import annotations

from pydantic import BaseModel


class TestProfile(BaseModel):
    """Which steps of the APK Tester state machine (Section 6.3) run."""

    __test__ = False

    name: str
    validate_manifest: bool = True
    install: bool = True
    launch: bool = True
    observe_logcat: bool = True
    observe_timeout_s: int = 15
    screenshot: bool = True
    check_permissions: bool = True
    extract_network_hosts: bool = True
    uninstall: bool = True


class Environment(BaseModel):
    """One entry from .droiddesk/environments.toml. See Section 6.8."""

    key: str
    label: str
    env_file: str
    firebase: str | None = None
    flavor: str | None = None
    api_host: str | None = None
    allow_release_build: bool = False
    require_clean_git: bool = False


class GuardResult(BaseModel):
    name: str
    passed: bool
    blocking: bool
    detail: str = ""
    overridden: bool = False


class CommandProfile(BaseModel):
    """A build command plus the guards evaluated before it runs. See Section 6.9."""

    name: str
    command: list[str]
    required_environment: str | None = None
    guard_environment_matches: bool = True
    guard_release_allowed: bool = False
    guard_git_clean: bool = True
    guard_secret_scan_clean: bool = True
    guard_no_debug_flags: bool = False
    guard_version_bumped: bool = False
