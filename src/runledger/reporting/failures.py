"""Human-readable failure explanations for `runledger run` console output.

Everything here is derived from data the runner already records (the case
``failure``, the ``assertion_failure`` / ``budget_failure`` trace events, and the
regression ``checks``). No new checks are performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from runledger.runner.models import CaseResult


@dataclass(frozen=True)
class CaseFailureDetail:
    case_id: str
    type: str
    message: str
    expected: str | None = None
    observed: str | None = None


@dataclass(frozen=True)
class GateFailureDetail:
    gate: str
    message: str


def _join_calls(calls: object) -> str:
    if isinstance(calls, (list, tuple)) and calls:
        return " -> ".join(str(item) for item in calls)
    return "<none>"


def _join_names(names: object) -> str:
    if isinstance(names, (list, tuple)) and names:
        return ", ".join(str(item) for item in names)
    return "<none>"


def _expected_observed(assertion_type: str, details: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    if not details:
        return None, None
    if assertion_type == "call_order":
        return (
            _join_calls(details.get("expected_order")),
            _join_calls(details.get("observed_calls")),
        )
    if assertion_type == "must_call":
        missing = details.get("missing")
        return (
            f"calls to: {_join_names(missing)}",
            _join_calls(details.get("observed_calls")),
        )
    if assertion_type == "must_not_call":
        forbidden = details.get("forbidden")
        return (
            f"no calls to: {_join_names(forbidden)}",
            _join_calls(details.get("observed_calls")),
        )
    if assertion_type == "required_fields":
        missing = details.get("missing")
        return (
            f"fields present: {_join_names(missing)}",
            f"missing: {_join_names(missing)}",
        )
    if assertion_type == "json_schema":
        path = details.get("path", "<root>")
        missing = details.get("missing")
        if missing:
            return (
                f"required field(s) at {path}: {_join_names(missing)}",
                f"missing: {_join_names(missing)}",
            )
        error = details.get("error")
        return (
            f"output valid against schema at {path}",
            str(error) if error is not None else None,
        )
    return None, None


def _trace_events(result: CaseResult, event_type: str) -> list[dict[str, Any]]:
    return [event for event in result.trace if event.get("type") == event_type]


def _assertion_details(result: CaseResult) -> list[CaseFailureDetail]:
    details: list[CaseFailureDetail] = []
    for event in _trace_events(result, "assertion_failure"):
        failures = event.get("failures")
        if not isinstance(failures, list):
            continue
        for item in failures:
            if not isinstance(item, dict):
                continue
            assertion_type = str(item.get("type") or "assertion")
            expected, observed = _expected_observed(assertion_type, item.get("details"))
            details.append(
                CaseFailureDetail(
                    case_id=result.case_id,
                    type=assertion_type,
                    message=str(item.get("message") or ""),
                    expected=expected,
                    observed=observed,
                )
            )
    if not details and result.failed_assertions:
        for item in result.failed_assertions:
            details.append(
                CaseFailureDetail(
                    case_id=result.case_id,
                    type=str(item.get("type") or "assertion"),
                    message=str(item.get("message") or ""),
                )
            )
    return details


def _budget_details(result: CaseResult) -> list[CaseFailureDetail]:
    details: list[CaseFailureDetail] = []
    for event in _trace_events(result, "budget_failure"):
        failures = event.get("failures")
        if not isinstance(failures, list):
            continue
        for item in failures:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field"))
            limit = item.get("limit")
            actual = item.get("actual")
            details.append(
                CaseFailureDetail(
                    case_id=result.case_id,
                    type=f"budget:{field}",
                    message=f"Budget exceeded: {field} limit={limit} actual={actual}",
                    expected=f"{field} <= {limit}",
                    observed=f"{actual}",
                )
            )
    return details


def collect_case_failures(results: Iterable[CaseResult]) -> list[CaseFailureDetail]:
    """Return one entry per failure reason for every failing case, in case order."""
    collected: list[CaseFailureDetail] = []
    for result in results:
        if result.passed:
            continue
        failure = result.failure
        entries: list[CaseFailureDetail] = []
        if failure is not None and failure.type == "assertion_failed":
            entries = _assertion_details(result)
        elif failure is not None and failure.type == "budget_exceeded":
            entries = _budget_details(result)
        if not entries:
            if failure is not None:
                entries = [
                    CaseFailureDetail(
                        case_id=result.case_id,
                        type=failure.type,
                        message=failure.message,
                    )
                ]
            else:
                entries = [
                    CaseFailureDetail(
                        case_id=result.case_id,
                        type="unknown",
                        message="Case failed without a recorded reason",
                    )
                ]
        collected.extend(entries)
    return collected


def _fmt_number(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def collect_gate_failures(regression: Mapping[str, Any] | None) -> list[GateFailureDetail]:
    """Return failing regression gate checks (e.g. min_pass_rate)."""
    if not regression:
        return []
    failures: list[GateFailureDetail] = []
    for check in regression.get("checks", []) or []:
        if not isinstance(check, dict) or check.get("status") != "fail":
            continue
        gate = str(check.get("id"))
        threshold = check.get("threshold")
        baseline = check.get("baseline")
        current = check.get("current")
        if gate == "min_pass_rate":
            message = (
                f"Regression gate min_pass_rate failed: pass_rate {_fmt_number(current)} "
                f"< required {_fmt_number(threshold)} (baseline {_fmt_number(baseline)})"
            )
        elif check.get("delta_pct") is not None:
            message = (
                f"Regression gate {gate} failed: delta_pct {_fmt_number(check.get('delta_pct'))} "
                f"> allowed {_fmt_number(threshold)} "
                f"(baseline {_fmt_number(baseline)}, current {_fmt_number(current)})"
            )
        else:
            message = (
                f"Regression gate {gate} failed: current {_fmt_number(current)}, "
                f"threshold {_fmt_number(threshold)}, baseline {_fmt_number(baseline)}"
            )
        note = check.get("note")
        if note:
            message = f"{message} ({note})"
        failures.append(GateFailureDetail(gate=gate, message=message))
    return failures


def _indent_continuation(value: str, width: int) -> str:
    lines = value.splitlines() or [""]
    pad = " " * width
    return ("\n" + pad).join(lines)


def format_failure_lines(
    case_failures: Sequence[CaseFailureDetail],
    gate_failures: Sequence[GateFailureDetail],
) -> list[str]:
    """Plain-text lines explaining why the run failed."""
    lines: list[str] = []
    if case_failures:
        case_ids = list(dict.fromkeys(item.case_id for item in case_failures))
        lines.append(f"Failures ({len(case_ids)} case{'s' if len(case_ids) != 1 else ''}):")
        for case_id in case_ids:
            lines.append("")
            lines.append(f"FAIL {case_id}")
            for item in case_failures:
                if item.case_id != case_id:
                    continue
                lines.append(f"  assertion: {item.type}")
                lines.append(f"  message:   {_indent_continuation(item.message, 13)}")
                if item.expected is not None:
                    lines.append(f"  expected:  {item.expected}")
                if item.observed is not None:
                    lines.append(f"  observed:  {item.observed}")
    if gate_failures:
        if lines:
            lines.append("")
        lines.append(f"Gate failures ({len(gate_failures)}):")
        for gate in gate_failures:
            lines.append(f"  {gate.gate}: {gate.message}")
    return lines


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(",", "%2C").replace("::", "%3A%3A")


def github_annotation_lines(
    case_failures: Sequence[CaseFailureDetail],
    gate_failures: Sequence[GateFailureDetail],
) -> list[str]:
    """GitHub Actions workflow commands (`::error ...`) for each failure."""
    lines: list[str] = []
    for item in case_failures:
        message = item.message
        title = _escape_property(f"runledger: {item.case_id}")
        lines.append(f"::error title={title}::{_escape_data(message)}")
    for gate in gate_failures:
        title = _escape_property(f"runledger: gate {gate.gate}")
        lines.append(f"::error title={title}::{_escape_data(gate.message)}")
    return lines
