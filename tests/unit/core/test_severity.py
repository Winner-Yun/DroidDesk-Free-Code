from droiddesk.core.severity import GateVerdict, Severity, Verdict


def test_severity_values_are_stable_strings() -> None:
    assert Severity.CRITICAL == "critical"
    assert Severity.NEEDS_REVIEW == "review"


def test_verdict_and_gate_verdict_are_distinct_enums() -> None:
    assert Verdict.PASS != GateVerdict.GO
    assert Verdict.PASS == "PASS"
