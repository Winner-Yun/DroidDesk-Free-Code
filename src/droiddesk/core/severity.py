"""Severity classifications and test verdict definitions."""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NEEDS_REVIEW = "review"
    INFORMATIONAL = "info"


class Verdict(StrEnum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS WITH WARNINGS"
    FAIL = "FAIL"
