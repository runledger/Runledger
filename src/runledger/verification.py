"""Repeat known-good replays and verify explicit, customer-authored regressions."""

from __future__ import annotations

import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from runledger import __version__
from runledger.artifacts.junit import write_junit
from runledger.artifacts.report import write_report
from runledger.artifacts.run_log import write_run_log
from runledger.artifacts.summary import build_summary, create_run_dir, write_summary
from runledger.baseline.io import load_baseline
from runledger.baseline.models import BaselineSummary
from runledger.config.loader import load_cases, load_suite, resolve_command_paths
from runledger.config.models import BudgetSpec, CaseConfig, SuiteConfig
from runledger.regression import compute_regression
from runledger.runner.budgets import merge_budgets
from runledger.runner.engine import run_suite
from runledger.runner.models import CaseResult, SuiteResult
from runledger.util.redaction import redact
from runledger.util.xml import sanitize_xml_text

AssertionName = Literal[
    "json_schema", "required_fields", "must_call", "must_not_call", "call_order"
]
BudgetName = Literal["max_wall_ms", "max_tool_calls", "max_tool_errors"]


class ExpectedFailure(BaseModel):
    assertion: AssertionName | None = None
    budget: BudgetName | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    message_contains: str | None = Field(default=None, min_length=1)
    tool_calls: int | None = Field(default=None, ge=0, strict=True)
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def one_failure_kind(self) -> ExpectedFailure:
        if (self.assertion is None) == (self.budget is None):
            raise ValueError("expect must specify exactly one of assertion or budget")
        json.dumps(self.details, allow_nan=False)
        return self


class RegressionProbe(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    case_id: str = Field(min_length=1)
    agent_command: list[str] | None = Field(default=None, min_length=1)
    input: dict[str, Any] | None = None
    expect: ExpectedFailure
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def has_mutation(self) -> RegressionProbe:
        if self.agent_command is None and self.input is None:
            raise ValueError("A regression needs agent_command or input")
        if self.agent_command is not None and not self.agent_command[0].strip():
            raise ValueError("agent_command needs a nonempty executable")
        json.dumps(self.input, allow_nan=False)
        return self


class VerificationPlan(BaseModel):
    schema_version: Literal[1]
    regressions: list[RegressionProbe] = Field(min_length=1)
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def strict_version(cls, data: Any) -> Any:
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
            raise ValueError("schema_version must be the integer 1")
        return data

    @model_validator(mode="after")
    def unique_names(self) -> VerificationPlan:
        names = [probe.name for probe in self.regressions]
        if len(set(names)) != len(names):
            raise ValueError("Regression names must be unique")
        return self


def load_plan(path: Path) -> VerificationPlan:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read verification plan {path}: {type(exc).__name__}") from exc
    plan = VerificationPlan.model_validate(data)
    for probe in plan.regressions:
        if probe.agent_command is not None:
            probe.agent_command = resolve_command_paths(probe.agent_command, path.parent)
    return plan


def behavior_sha256(case: CaseResult) -> str:
    """Keep payload fields intact; discard only protocol envelope bookkeeping."""
    behavior = []
    for event in case.trace:
        kind = event.get("type")
        if kind == "tool_call":
            behavior.append({"type": kind, "name": event["name"], "args": event["args"]})
        elif kind == "tool_result":
            behavior.append(
                {
                    "type": kind,
                    "ok": event["ok"],
                    "result": event.get("result"),
                    "error": event.get("error"),
                }
            )
        elif kind == "final_output":
            behavior.append({"type": kind, "output": event["output"]})
    encoded = json.dumps(
        behavior, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_contains(left, right) for left, right in zip(actual, expected))
        )
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    return actual == expected


def match_expected_failure(case: CaseResult, expected: ExpectedFailure) -> tuple[bool, str]:
    if case.passed or case.failure is None:
        return False, "The deliberately broken case passed"
    kind = "assertion_failed" if expected.assertion else "budget_exceeded"
    if case.failure.type != kind:
        return False, f"Expected {kind}; got {case.failure.type}: {case.failure.message}"
    event_type = "assertion_failure" if expected.assertion else "budget_failure"
    failures = [
        failure
        for event in case.trace
        if event.get("type") == event_type
        for failure in event["failures"]
    ]
    other_type = "budget_failure" if expected.assertion else "assertion_failure"
    if any(event.get("type") == other_type for event in case.trace):
        return False, "An additional, unrelated failure occurred"
    if len(failures) != 1:
        return False, f"Expected exactly one failure; got {len(failures)}"
    failure = failures[0]
    field = "type" if expected.assertion else "field"
    target = expected.assertion or expected.budget
    if failure.get(field) != target:
        return False, f"Expected {target}; got {failure.get(field)}"
    details = failure.get("details", {}) if expected.assertion else failure
    if not _contains(details, expected.details):
        return False, "Failure details do not match the expected regression"
    if expected.message_contains and expected.message_contains not in case.failure.message:
        return False, "Failure message does not identify the expected regression"
    if expected.tool_calls is not None and case.tool_calls != expected.tool_calls:
        return False, f"Expected {expected.tool_calls} tool calls; got {case.tool_calls}"
    if expected.assertion and case.output is None:
        return False, "Assertion verification requires an actual final output"
    return True, f"Detected expected {target} failure"


def bounded_cases(suite: SuiteConfig, cases: list[CaseConfig], timeout: float) -> list[CaseConfig]:
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number of seconds")
    cap = max(1, int(timeout * 1000))
    bounded = []
    for original in cases:
        case = original.model_copy(deep=True)
        budget = merge_budgets(suite.budgets, case.budgets) or BudgetSpec()
        wall = budget.max_wall_ms
        case.budgets = budget.model_copy(
            update={"max_wall_ms": min(wall, cap) if wall is not None else cap}
        )
        bounded.append(case)
    return bounded


def run_with_artifacts(
    suite: SuiteConfig,
    cases: list[CaseConfig],
    path: Path,
    source: Path,
    *,
    compare_baseline: bool = False,
) -> tuple[SuiteResult, bool]:
    """Run replay copies; artifacts retain the actual (possibly expected-failing) result."""
    path.mkdir(parents=True, exist_ok=False)
    result = run_suite(suite, cases)
    regression = None
    if compare_baseline and suite.baseline_path:
        current = BaselineSummary.model_validate(
            build_summary(suite=suite, suite_path=source, suite_result=result, run_id=path.name)
        )
        regression = compute_regression(
            baseline=load_baseline(Path(suite.baseline_path)),
            current=current,
            thresholds=suite.regression,
            baseline_path=Path(suite.baseline_path),
        )
    summary = build_summary(
        suite=suite, suite_path=source, suite_result=result, run_id=path.name, regression=regression
    )
    write_run_log(path, result.cases)
    write_summary(
        path,
        suite=suite,
        suite_path=source,
        suite_result=result,
        run_id=path.name,
        regression=regression,
    )
    write_junit(path, suite.suite_name, result.cases, regression=regression)
    # Raw failing probe results must not be mistaken for verification failures by a
    # generic **/junit.xml collector. The aggregate file is the CI gate for verify.
    (path / "junit.xml").rename(path / "probe.junit.xml")
    write_report(path, summary=summary, run_log_path=path / "run.jsonl")
    return result, result.passed and (regression is None or regression.get("passed", True))


def _write_evidence(path: Path, report: dict[str, Any]) -> None:
    clean = redact(report)
    (path / "verification.json").write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
    checks = list(clean["checks"])
    if clean.get("error"):
        checks.append({"name": "verification-error", "passed": False, "message": clean["error"]})
    root = ET.Element(
        "testsuite",
        name="RunLedger verification",
        tests=str(len(checks)),
        failures=str(sum(not check["passed"] for check in checks)),
    )
    for check in checks:
        node = ET.SubElement(
            root, "testcase", name=sanitize_xml_text(check["name"]), classname="runledger.verify"
        )
        if not check["passed"]:
            message = sanitize_xml_text(check["message"])
            ET.SubElement(node, "failure", message=message).text = message
    ET.ElementTree(root).write(
        path / "verification.junit.xml", encoding="utf-8", xml_declaration=True
    )


def verify_suite(
    suite_path: Path,
    plan_path: Path,
    *,
    repeats: int = 3,
    timeout: float = 30.0,
    output_dir: Path = Path("runledger_out"),
) -> dict[str, Any]:
    if type(repeats) is not int or not 1 <= repeats <= 100:
        raise ValueError("repeats must be an integer from 1 to 100")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number of seconds")
    source = (suite_path / "suite.yaml" if suite_path.is_dir() else suite_path).resolve()
    suite = load_suite(source).model_copy(deep=True, update={"mode": "replay"})
    cases = load_cases(source.parent, suite.cases_path)
    by_id = {case.id: case for case in cases}
    if len(by_id) != len(cases):
        raise ValueError("Case IDs must be unique")
    plan = load_plan(plan_path.resolve())
    for probe in plan.regressions:
        if probe.case_id not in by_id:
            raise ValueError(f"Unknown regression case_id: {probe.case_id}")
        case = by_id[probe.case_id]
        if probe.expect.assertion:
            assertions = suite.assertions + (case.assertions or [])
            if not any(spec.type == probe.expect.assertion for spec in assertions):
                raise ValueError(f"{probe.name}: expected assertion is not configured on this case")
        else:
            budget = merge_budgets(suite.budgets, case.budgets)
            limit = getattr(budget, probe.expect.budget, None)
            if limit is None:
                raise ValueError(f"{probe.name}: expected budget is not configured on this case")
            if probe.expect.budget == "max_wall_ms" and limit > timeout * 1000:
                raise ValueError(
                    f"{probe.name}: timeout must cover the configured wall-time budget"
                )
    # Validate the baseline before executing any customer agent.
    if suite.baseline_path:
        load_baseline(Path(suite.baseline_path))
    directory, run_id = create_run_dir(output_dir, "verification")
    report: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "runledger_version": __version__,
        "suite_path": str(source),
        "plan_path": str(plan_path.resolve()),
        "repeats": repeats,
        "timeout_seconds": timeout,
        "mode": "replay",
        "artifact_directory": str(directory.resolve()),
        "checks": [],
        "passed": False,
    }
    fingerprints: dict[str, str] = {}

    def good_run(name: str, selected: list[CaseConfig], *, full_suite: bool) -> bool:
        result, passed = run_with_artifacts(
            suite.model_copy(deep=True),
            bounded_cases(suite, selected, timeout),
            directory / name,
            source,
            compare_baseline=full_suite,
        )
        signatures = {case.case_id: behavior_sha256(case) for case in result.cases}
        drift = [
            key
            for key, value in signatures.items()
            if key in fingerprints and fingerprints[key] != value
        ]
        passed = passed and not drift
        message = "Known-good replay passed with unchanged behavior"
        if not result.passed:
            message = "; ".join(
                f"{case.case_id}: {case.failure.message if case.failure else 'failed'}"
                for case in result.cases
                if not case.passed
            )
        elif drift:
            message = "Behavior changed for: " + ", ".join(drift)
        elif not passed:
            message = "Baseline regression gate failed"
        report["checks"].append(
            {
                "name": name,
                "passed": passed,
                "message": message,
                "artifacts": name,
                "behavior_sha256": [
                    {"case_id": case_id, "sha256": digest}
                    for case_id, digest in sorted(signatures.items())
                ],
            }
        )
        if passed:
            fingerprints.update(signatures)
        return passed

    try:
        for number in range(1, repeats + 1):
            if not good_run(f"unchanged-{number:02}", cases, full_suite=True):
                return report
        for number, probe in enumerate(plan.regressions, 1):
            name = f"regression-{number:02}-{probe.name}"
            mutated_suite = suite.model_copy(deep=True)
            mutated_case = by_id[probe.case_id].model_copy(deep=True)
            if probe.agent_command is not None:
                mutated_suite.agent_command = list(probe.agent_command)
            if probe.input is not None:
                mutated_case.input = dict(probe.input)
            result, _ = run_with_artifacts(
                mutated_suite,
                bounded_cases(mutated_suite, [mutated_case], timeout),
                directory / name,
                source,
            )
            case = result.cases[0]
            passed, message = match_expected_failure(case, probe.expect)
            report["checks"].append(
                {
                    "name": name,
                    "passed": passed,
                    "message": message,
                    "artifacts": name,
                    "expected": probe.expect.model_dump(exclude_none=True),
                    "actual_failure_type": case.failure.type if case.failure else None,
                    "tool_calls": case.tool_calls,
                }
            )
            # Always verify the original case after a negative probe, even when the
            # probe failed unexpectedly. No source/config/cassette edits are needed.
            if not good_run(
                f"recovery-{number:02}-{probe.name}", [by_id[probe.case_id]], full_suite=False
            ):
                break
        report["passed"] = bool(report["checks"]) and all(
            check["passed"] for check in report["checks"]
        )
    except Exception as exc:  # noqa: BLE001 - retain evidence for any execution/artifact failure
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        _write_evidence(directory, report)
    return report
