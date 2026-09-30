from __future__ import annotations

from runledger.reporting import (
    collect_case_failures,
    collect_gate_failures,
    format_failure_lines,
    github_annotation_lines,
)
from runledger.runner.models import CaseResult, Failure


def _case(case_id: str, *, passed: bool, failure: Failure | None, trace: list[dict]) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        passed=passed,
        output={"ok": True},
        trace=trace,
        wall_ms=1,
        tool_calls=0,
        tool_errors=0,
        failure=failure,
    )


def _call_order_case() -> CaseResult:
    return _case(
        "refund_after_lookup",
        passed=False,
        failure=Failure(
            type="assertion_failed",
            message="Tool call order not satisfied: lookup_order -> issue_refund",
        ),
        trace=[
            {"type": "tool_call", "name": "issue_refund"},
            {"type": "tool_call", "name": "lookup_order"},
            {
                "type": "assertion_failure",
                "failures": [
                    {
                        "type": "call_order",
                        "message": "Tool call order not satisfied: lookup_order -> issue_refund",
                        "details": {
                            "expected_order": ["lookup_order", "issue_refund"],
                            "observed_calls": ["issue_refund", "lookup_order"],
                        },
                    }
                ],
            },
        ],
    )


def test_call_order_failure_has_expected_and_observed() -> None:
    passing = _case("ok_case", passed=True, failure=None, trace=[])
    failures = collect_case_failures([passing, _call_order_case()])

    assert len(failures) == 1
    item = failures[0]
    assert item.case_id == "refund_after_lookup"
    assert item.type == "call_order"
    assert item.message == "Tool call order not satisfied: lookup_order -> issue_refund"
    assert item.expected == "lookup_order -> issue_refund"
    assert item.observed == "issue_refund -> lookup_order"

    lines = format_failure_lines(failures, [])
    text = "\n".join(lines)
    assert "FAIL refund_after_lookup" in text
    assert "  assertion: call_order" in text
    assert "  message:   Tool call order not satisfied: lookup_order -> issue_refund" in text
    assert "  expected:  lookup_order -> issue_refund" in text
    assert "  observed:  issue_refund -> lookup_order" in text


def test_must_call_and_schema_failures() -> None:
    result = _case(
        "t2",
        passed=False,
        failure=Failure(type="assertion_failed", message="x"),
        trace=[
            {
                "type": "assertion_failure",
                "failures": [
                    {
                        "type": "must_call",
                        "message": "Missing required tool calls: lookup_order. Observed: <none>",
                        "details": {"missing": ["lookup_order"], "observed_calls": []},
                    },
                    {
                        "type": "json_schema",
                        "message": "Schema validation failed at <root>: missing required field(s): reply",
                        "details": {"path": "<root>", "error": "'reply' is a required property", "missing": ["reply"]},
                    },
                ],
            }
        ],
    )
    failures = collect_case_failures([result])
    assert [f.type for f in failures] == ["must_call", "json_schema"]
    assert failures[0].expected == "calls to: lookup_order"
    assert failures[0].observed == "<none>"
    assert failures[1].observed == "missing: reply"


def test_budget_and_runtime_failures() -> None:
    budget = _case(
        "b1",
        passed=False,
        failure=Failure(type="budget_exceeded", message="Budget exceeded: max_tool_calls limit=1 actual=3"),
        trace=[
            {
                "type": "budget_failure",
                "failures": [{"field": "max_tool_calls", "limit": 1, "actual": 3}],
            }
        ],
    )
    runtime = _case(
        "c1",
        passed=False,
        failure=Failure(type="cassette_mismatch", message="No cassette entry for tool search_docs"),
        trace=[],
    )
    failures = collect_case_failures([budget, runtime])
    assert failures[0].type == "budget:max_tool_calls"
    assert failures[0].expected == "max_tool_calls <= 1"
    assert failures[0].observed == "3"
    assert failures[1].type == "cassette_mismatch"
    assert failures[1].message == "No cassette entry for tool search_docs"
    assert failures[1].expected is None


def test_gate_failures_only_include_failed_checks() -> None:
    regression = {
        "passed": False,
        "checks": [
            {"id": "min_pass_rate", "status": "fail", "threshold": 1.0, "baseline": 1.0, "current": 0.5},
            {"id": "max_avg_wall_ms_delta_pct", "status": "pass", "threshold": 10.0, "delta_pct": 0.1},
            {"id": "max_p95_wall_ms_delta_pct", "status": "skipped", "threshold": None},
        ],
    }
    gates = collect_gate_failures(regression)
    assert [g.gate for g in gates] == ["min_pass_rate"]
    assert "pass_rate 0.5000 < required 1.0000" in gates[0].message
    assert collect_gate_failures(None) == []

    text = "\n".join(format_failure_lines([], gates))
    assert "Gate failures (1):" in text
    assert "min_pass_rate: Regression gate min_pass_rate failed" in text


def test_github_annotations_format_and_escaping() -> None:
    failures = collect_case_failures([_call_order_case()])
    gates = collect_gate_failures(
        {"checks": [{"id": "min_pass_rate", "status": "fail", "threshold": 1.0, "baseline": 1.0, "current": 0.0}]}
    )
    lines = github_annotation_lines(failures, gates)
    assert lines[0] == (
        "::error title=runledger: refund_after_lookup::"
        "Tool call order not satisfied: lookup_order -> issue_refund"
    )
    assert lines[1].startswith("::error title=runledger: gate min_pass_rate::Regression gate min_pass_rate failed")

    multi = _case(
        "a,b",
        passed=False,
        failure=Failure(type="task_error", message="line1\nline2 100%"),
        trace=[],
    )
    (line,) = github_annotation_lines(collect_case_failures([multi]), [])
    assert line == "::error title=runledger: a%2Cb::line1%0Aline2 100%25"
