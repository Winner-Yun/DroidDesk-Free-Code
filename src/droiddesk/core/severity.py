"""Finding classification. See Section 6.5 — classification is the product: a
scanner that reports every match at the same severity trains the user to ignore it.
"""

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


class GateVerdict(StrEnum):
    GO = "GO"
    BLOCKED = "BLOCKED"
    OVERRIDDEN = "OVERRIDDEN"
