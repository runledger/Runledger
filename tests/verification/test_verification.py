from __future__ import annotations

import copy
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from runledger.runner.models import CaseResult, Failure
from runledger.util.xml import sanitize_xml_text
from runledger.verification import (
    ExpectedFailure,
    behavior_sha256,
    load_plan,
    match_expected_failure,
    verify_suite,
)

# This agent exchanges real JSONL with the runner. Its mutations change behavior,
# not assertions or runner results, so infrastructure failures cannot stand in for
# successfully detecting the intended regression.
AGENT = """import json
import sys
import time
from pathlib import Path

request = json.loads(sys.stdin.readline())
data = request["input"]
scenario = sys.argv[1] if len(sys.argv) > 1 else data.get("scenario", "skip")
state = Path(__file__).with_name("agent-state.txt")

def emit(payload):
    print(json.dumps(payload), flush=True)

if scenario == "crash":
    raise RuntimeError("deliberate startup crash")
if scenario == "task-error":
    emit({"type": "task_error", "message": "deliberate task failure"})
    sys.exit(0)
if scenario == "hang":
    time.sleep(10)
if scenario == "poison":
    state.write_text("changed", encoding="utf-8")

if scenario not in {"skip", "multiple", "poison"}:
    query = "missing" if scenario == "mismatch" else "hello"
    if scenario == "tool-error":
        query = "error"
    for index in range(2 if scenario == "extra-call" else 1):
        emit({"type": "tool_call", "call_id": str(time.time_ns()) + str(index),
              "name": "lookup", "args": {"q": query}})
        if not sys.stdin.readline():
            sys.exit(0)

answer = "hello"
if scenario == "repeat-drift":
    number = int(state.read_text()) + 1 if state.exists() else 1
    state.write_text(str(number), encoding="utf-8")
    answer = str(number)
elif scenario == "recovery-drift" and state.exists():
    answer = state.read_text(encoding="utf-8")
output = {} if scenario in {"missing-field", "multiple"} else {"answer": answer}
emit({"type": "final_output", "output": output})
"""


@dataclass
class SuiteFiles:
    root: Path
    suite: Path
    case: Path
    plan: Path
    agent: Path

    def plan_for(self, probes: list[dict[str, Any]]) -> None:
        self.plan.write_text(
            yaml.safe_dump({"schema_version": 1, "regressions": probes}), encoding="utf-8"
        )

    def update_case(self, **updates: Any) -> None:
        data = yaml.safe_load(self.case.read_text(encoding="utf-8"))
        data.update(updates)
        self.case.write_text(yaml.safe_dump(data), encoding="utf-8")

    def update_suite(self, **updates: Any) -> None:
        data = yaml.safe_load(self.suite.read_text(encoding="utf-8"))
        data.update(updates)
        self.suite.write_text(yaml.safe_dump(data), encoding="utf-8")

    def verify(self, **options: Any) -> dict[str, Any]:
        return verify_suite(self.suite, self.plan, output_dir=self.root / "out", **options)


def probe(scenario: str = "skip", **updates: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": scenario,
        "case_id": "c1",
        "input": {"scenario": scenario},
        "expect": {
            "assertion": "must_call",
            "details": {"missing": ["lookup"], "observed_calls": []},
            "tool_calls": 0,
            "message_contains": "Missing required tool calls",
        },
    }
    data.update(updates)
    return data


@pytest.fixture
def suite_files(tmp_path: Path) -> SuiteFiles:
    root = tmp_path / "suite with spaces"
    (root / "cases").mkdir(parents=True)
    agent = root / "agent child.py"
    agent.write_text(AGENT, encoding="utf-8")
    suite = root / "suite.yaml"
    suite.write_text(
        yaml.safe_dump(
            {
                "suite_name": "verification-test",
                "agent_command": [sys.executable, str(agent)],
                "mode": "replay",
                "cases_path": "cases",
                "tool_registry": ["lookup"],
                "assertions": [
                    {"type": "must_call", "tools": ["lookup"]},
                    {"type": "json_schema", "schema_path": "schema.json"},
                ],
                "budgets": {"max_tool_calls": 1, "max_tool_errors": 0},
            }
        ),
        encoding="utf-8",
    )
    (root / "schema.json").write_text(
        json.dumps({"type": "object", "required": ["answer"]}), encoding="utf-8"
    )
    case = root / "cases" / "c1.yaml"
    case.write_text(
        yaml.safe_dump({"id": "c1", "input": {"scenario": "pass"}, "cassette": "cassette.jsonl"}),
        encoding="utf-8",
    )
    (root / "cassette.jsonl").write_text(
        "\n".join(
            json.dumps(entry)
            for entry in [
                {
                    "tool": "lookup",
                    "args": {"q": "hello"},
                    "ok": True,
                    "result": {"answer": "hello"},
                },
                {
                    "tool": "lookup",
                    "args": {"q": "error"},
                    "ok": False,
                    "error": {"code": "expected-fixture-error"},
                },
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    files = SuiteFiles(root, suite, case, root / "verification.yaml", agent)
    files.plan_for([probe()])
    return files


def _checks(report: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    return [check for check in report["checks"] if check["name"].startswith(prefix)]


def _artifact(report: dict[str, Any], check: dict[str, Any], filename: str) -> Path:
    return Path(report["artifact_directory"]) / check["artifacts"] / filename


def test_real_replays_assertions_budgets_recovery_and_artifacts(suite_files: SuiteFiles) -> None:
    suite_files.plan_for(
        [
            probe(),
            probe(
                "missing-field",
                expect={
                    "assertion": "json_schema",
                    "details": {"missing": ["answer"]},
                    "tool_calls": 1,
                },
            ),
            probe(
                "extra-call",
                expect={
                    "budget": "max_tool_calls",
                    "details": {"limit": 1, "actual": 2},
                    "tool_calls": 2,
                },
            ),
            probe(
                "tool-error",
                expect={
                    "budget": "max_tool_errors",
                    "details": {"limit": 0, "actual": 1},
                    "tool_calls": 1,
                },
            ),
        ]
    )
    # Verify forces replay even when a source suite requests recording.
    suite_files.update_suite(mode="record", tool_module="must_not_be_imported")
    sources = {path: path.read_bytes() for path in suite_files.root.rglob("*") if path.is_file()}
    report = suite_files.verify(repeats=3)
    assert report["passed"], report
    assert len(report["checks"]) == 11
    assert len(_checks(report, "unchanged-")) == 3
    assert len(_checks(report, "recovery-")) == 4
    fingerprints = [
        check["behavior_sha256"][0]["sha256"]
        for check in report["checks"]
        if "behavior_sha256" in check
    ]
    assert len(set(fingerprints)) == 1
    assert all(path.read_bytes() == original for path, original in sources.items())
    directory = Path(report["artifact_directory"])
    assert json.loads((directory / "verification.json").read_text()) == report
    junit = ET.parse(directory / "verification.junit.xml").getroot()
    assert junit.get("tests") == "11"
    assert junit.get("failures") == "0"
    assert not junit.findall(".//failure")
    assert not list(directory.rglob("junit.xml"))
    for check in report["checks"]:
        for name in ("summary.json", "run.jsonl", "report.html", "probe.junit.xml"):
            assert _artifact(report, check, name).is_file()
    for check in _checks(report, "regression-"):
        assert (
            ET.parse(_artifact(report, check, "probe.junit.xml")).getroot().get("failures") == "1"
        )


@pytest.mark.parametrize(
    ("scenario", "expected_reason"),
    [
        ("pass", "deliberately broken case passed"),
        ("missing-field", "Expected must_call; got json_schema"),
        ("multiple", "Expected exactly one failure; got 2"),
        ("crash", "got agent_error"),
        ("task-error", "got task_error"),
        ("mismatch", "got cassette_mismatch"),
    ],
)
def test_unrelated_failures_never_count_as_detected_regressions(
    suite_files: SuiteFiles, scenario: str, expected_reason: str
) -> None:
    suite_files.plan_for([probe(scenario)])
    report = suite_files.verify(repeats=1)
    assert not report["passed"]
    check = _checks(report, "regression-")[0]
    assert not check["passed"]
    assert expected_reason in check["message"]
    assert _checks(report, "recovery-")[0]["passed"]
    junit = ET.parse(Path(report["artifact_directory"]) / "verification.junit.xml").getroot()
    assert junit.get("failures") == "1"


def test_missing_agent_executable_does_not_satisfy_assertion(suite_files: SuiteFiles) -> None:
    suite_files.plan_for([probe(agent_command=[str(suite_files.root / "missing-program")])])
    report = suite_files.verify(repeats=1)
    assert not report["passed"]
    assert _checks(report, "regression-")[0]["actual_failure_type"] == "agent_error"
    assert _checks(report, "recovery-")[0]["passed"]


def test_repeat_drift_fails_even_when_all_contracts_pass(suite_files: SuiteFiles) -> None:
    suite_files.update_case(input={"scenario": "repeat-drift"})
    report = suite_files.verify(repeats=3)
    assert not report["passed"]
    assert len(report["checks"]) == 2
    assert report["checks"][0]["passed"]
    assert not report["checks"][1]["passed"]
    assert "Behavior changed for: c1" in report["checks"][1]["message"]
    summary = json.loads(_artifact(report, report["checks"][1], "summary.json").read_text())
    assert summary["cases"][0]["status"] == "pass"


def test_recovery_drift_fails_after_expected_negative(suite_files: SuiteFiles) -> None:
    suite_files.update_case(input={"scenario": "recovery-drift"})
    suite_files.plan_for([probe("poison")])
    report = suite_files.verify(repeats=2)
    assert not report["passed"]
    assert _checks(report, "regression-")[0]["passed"]
    recovery = _checks(report, "recovery-")[0]
    assert not recovery["passed"]
    assert "Behavior changed for: c1" in recovery["message"]


def test_empty_input_replaces_original_input(suite_files: SuiteFiles) -> None:
    suite_files.plan_for([probe(input={})])
    report = suite_files.verify(repeats=1)
    assert report["passed"], report
    negative = _checks(report, "regression-")[0]
    events = [
        json.loads(line)
        for line in _artifact(report, negative, "run.jsonl").read_text().splitlines()
    ]
    assert next(event for event in events if event["type"] == "task_start")["input"] == {}


def test_override_command_resolves_from_nested_plan(suite_files: SuiteFiles) -> None:
    folder = suite_files.root / "nested plan"
    folder.mkdir()
    (folder / "mutation script.py").write_text(AGENT, encoding="utf-8")
    suite_files.plan = folder / "verification.yaml"
    mutation = probe(agent_command=[sys.executable, "mutation script.py", "skip"])
    mutation.pop("input")
    suite_files.plan_for([mutation])
    report = suite_files.verify(repeats=1)
    assert report["passed"], report


def test_safety_timeout_cannot_satisfy_an_assertion(suite_files: SuiteFiles) -> None:
    suite_files.plan_for([probe("hang")])
    report = suite_files.verify(repeats=1, timeout=1.0)
    assert not report["passed"]
    negative = _checks(report, "regression-")[0]
    assert negative["actual_failure_type"] == "budget_exceeded"
    assert not negative["passed"]
    assert _checks(report, "recovery-")[0]["passed"]


@pytest.mark.parametrize("wall", [None, 2000])
def test_safety_cap_cannot_masquerade_as_configured_wall_budget(
    suite_files: SuiteFiles, wall: int | None
) -> None:
    suite_files.update_suite(budgets={"max_wall_ms": wall})
    suite_files.plan_for([probe("hang", expect={"budget": "max_wall_ms"})])
    with pytest.raises(ValueError, match="not configured|timeout must cover"):
        suite_files.verify(repeats=1, timeout=0.5)
    assert not (suite_files.root / "out").exists()


def test_configured_wall_budget_is_verified(suite_files: SuiteFiles) -> None:
    suite_files.update_suite(budgets={"max_wall_ms": 1000})
    suite_files.plan_for(
        [
            probe(
                "hang",
                expect={"budget": "max_wall_ms", "details": {"limit": 1000}, "tool_calls": 0},
            )
        ]
    )
    report = suite_files.verify(repeats=1, timeout=3.0)
    assert report["passed"], report


def test_all_cases_are_repeated_but_only_mutated_case_is_recovered(suite_files: SuiteFiles) -> None:
    second = yaml.safe_load(suite_files.case.read_text(encoding="utf-8"))
    second["id"] = "c2"
    (suite_files.case.parent / "c2.yaml").write_text(yaml.safe_dump(second), encoding="utf-8")
    report = suite_files.verify(repeats=2)
    assert report["passed"], report
    for check in _checks(report, "unchanged-"):
        assert {entry["case_id"] for entry in check["behavior_sha256"]} == {"c1", "c2"}
    assert {entry["case_id"] for entry in _checks(report, "recovery-")[0]["behavior_sha256"]} == {
        "c1"
    }


def test_password_case_ids_keep_auditable_hashes_in_saved_evidence(suite_files: SuiteFiles) -> None:
    suite_files.update_case(id="password-reset")
    suite_files.plan_for([probe(case_id="password-reset")])
    report = suite_files.verify(repeats=2)
    assert report["passed"], report
    path = Path(report["artifact_directory"]) / "verification.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    for check in _checks(saved, "unchanged-") + _checks(saved, "recovery-"):
        assert len(check["behavior_sha256"]) == 1
        record = check["behavior_sha256"][0]
        assert record["case_id"] == "password-reset"
        assert len(record["sha256"]) == 64
        assert all(character in "0123456789abcdef" for character in record["sha256"])


def test_baseline_gate_failure_fails_verification_despite_passing_cases(
    suite_files: SuiteFiles,
) -> None:
    baseline = {
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "runledger_version": "0.2.4",
        "run": {"run_id": "baseline", "mode": "replay", "exit_status": "success"},
        "suite": {
            "name": "verification-test",
            "suite_path": str(suite_files.suite),
            "agent_command": [sys.executable, str(suite_files.agent)],
            "tool_mode": "replay",
        },
        "aggregates": {
            "cases_total": 1,
            "cases_pass": 1,
            "cases_fail": 0,
            "cases_error": 0,
            "pass_rate": 1.0,
            "metrics": {"wall_ms": {"mean": 0.001, "p95": 0.001}},
        },
        "cases": [
            {
                "id": "c1",
                "status": "pass",
                "wall_ms": 0,
                "tool_calls": 1,
                "tool_errors": 0,
                "assertions": {"total": 2, "failed": 0},
            }
        ],
    }
    path = suite_files.root / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    original = path.read_bytes()
    suite_files.update_suite(
        baseline_path="baseline.json", regression={"max_avg_wall_ms_delta_pct": 0}
    )
    report = suite_files.verify(repeats=2)
    assert not report["passed"]
    assert len(report["checks"]) == 1
    check = report["checks"][0]
    assert check["message"] == "Baseline regression gate failed"
    summary = json.loads(_artifact(report, check, "summary.json").read_text())
    assert summary["cases"][0]["status"] == "pass"
    assert summary["regression"]["passed"] is False
    assert path.read_bytes() == original
    assert (
        ET.parse(Path(report["artifact_directory"]) / "verification.junit.xml")
        .getroot()
        .get("failures")
        == "1"
    )


def test_invalid_baseline_is_rejected_before_running_agent(suite_files: SuiteFiles) -> None:
    suite_files.update_suite(baseline_path="baseline.json")
    (suite_files.root / "baseline.json").write_text("{}", encoding="utf-8")
    suite_files.update_case(input={"scenario": "repeat-drift"})
    with pytest.raises(ValueError):
        suite_files.verify()
    assert not (suite_files.root / "agent-state.txt").exists()
    assert not (suite_files.root / "out").exists()


def test_verification_artifacts_redact_unexpected_failure_secrets(suite_files: SuiteFiles) -> None:
    secret = "ghp_" + "a" * 36
    suite_files.agent.write_text(
        AGENT.replace('"deliberate task failure"', repr("failure " + secret)), encoding="utf-8"
    )
    suite_files.plan_for([probe("task-error")])
    report = suite_files.verify(repeats=1)
    assert not report["passed"]
    directory = Path(report["artifact_directory"])
    for filename in ("verification.json", "verification.junit.xml"):
        text = (directory / filename).read_text(encoding="utf-8")
        assert secret not in text
        assert "[REDACTED]" in text
    evidence = json.loads((directory / "verification.json").read_text(encoding="utf-8"))
    assert "[REDACTED]" in _checks(evidence, "regression-")[0]["message"]


def test_verification_junit_remains_parseable_with_control_characters(
    suite_files: SuiteFiles,
) -> None:
    suite_files.agent.write_text(
        AGENT.replace('"deliberate task failure"', repr("external error\x00\x1b[31m")),
        encoding="utf-8",
    )
    suite_files.plan_for([probe("task-error")])
    report = suite_files.verify(repeats=1)
    assert not report["passed"]
    path = Path(report["artifact_directory"]) / "verification.junit.xml"
    root = ET.parse(path).getroot()
    assert root.get("failures") == "1"
    assert "external error\ufffd\ufffd[31m" in root.find(".//failure").get("message", "")
    for raw_path in path.parent.rglob("probe.junit.xml"):
        ET.parse(raw_path)


def test_xml_text_preserves_legal_unicode_and_replaces_invalid_code_points() -> None:
    legal = "tab\tline\nreturn\r accented caf\u00e9 and \U0001f642"
    assert sanitize_xml_text(legal) == legal
    assert sanitize_xml_text("\x00\x08\x0b\x0c\x0e\x1f\ud800\udfff\ufffe\uffff") == "\ufffd" * 10


@pytest.mark.parametrize(
    "document",
    [
        {"schema_version": True, "regressions": [probe()]},
        {"schema_version": 1.0, "regressions": [probe()]},
        {"schema_version": 2, "regressions": [probe()]},
        {"schema_version": 1, "regressions": []},
        {"schema_version": 1, "regressions": [probe(), probe()]},
        {"schema_version": 1, "regressions": [probe()], "typo": True},
        {"schema_version": 1, "regressions": [probe(name="../escape")]},
        {"schema_version": 1, "regressions": [probe(agent_command=[])]},
        {"schema_version": 1, "regressions": [probe(agent_command=[" "])]},
        {"schema_version": 1, "regressions": [probe(typo=True)]},
        {"schema_version": 1, "regressions": [probe(expect={"assertion": "must_cal"})]},
        {"schema_version": 1, "regressions": [probe(expect={"budget": "max_tokens_out"})]},
        {
            "schema_version": 1,
            "regressions": [probe(expect={"assertion": "must_call", "budget": "max_tool_calls"})],
        },
        {
            "schema_version": 1,
            "regressions": [probe(expect={"assertion": "must_call", "tool_calls": True})],
        },
        {
            "schema_version": 1,
            "regressions": [
                probe(expect={"assertion": "must_call", "details": {"value": float("nan")}})
            ],
        },
    ],
)
def test_invalid_plans_are_rejected(tmp_path: Path, document: dict[str, Any]) -> None:
    path = tmp_path / "verification.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ValueError):
        load_plan(path)


def test_missing_mutation_and_malformed_yaml_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "verification.yaml"
    mutation = probe()
    mutation.pop("input")
    path.write_text(yaml.safe_dump({"schema_version": 1, "regressions": [mutation]}))
    with pytest.raises(ValueError, match="needs agent_command or input"):
        load_plan(path)
    path.write_text("regressions: [unterminated", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot read verification plan"):
        load_plan(path)


@pytest.mark.parametrize(
    "problem", ["unknown-case", "duplicate-case", "missing-assertion", "missing-budget"]
)
def test_invalid_suite_plan_relationship_is_rejected_before_execution(
    suite_files: SuiteFiles, problem: str
) -> None:
    if problem == "unknown-case":
        suite_files.plan_for([probe(case_id="unknown")])
    elif problem == "duplicate-case":
        (suite_files.case.parent / "duplicate.yaml").write_bytes(suite_files.case.read_bytes())
    elif problem == "missing-assertion":
        suite_files.plan_for([probe(expect={"assertion": "call_order"})])
    else:
        suite_files.plan_for([probe(expect={"budget": "max_wall_ms"})])
    with pytest.raises(ValueError):
        suite_files.verify()
    assert not (suite_files.root / "out").exists()


@pytest.mark.parametrize(
    "options",
    [
        {"repeats": True},
        {"repeats": 0},
        {"repeats": 101},
        {"repeats": 1.5},
        {"timeout": True},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": float("inf")},
        {"timeout": float("nan")},
    ],
)
def test_invalid_run_limits_are_rejected(suite_files: SuiteFiles, options: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        suite_files.verify(**options)


def _result(trace: list[dict[str, Any]]) -> CaseResult:
    return CaseResult(
        case_id="c1",
        passed=True,
        output={"answer": "hello"},
        trace=trace,
        wall_ms=1,
        tool_calls=1,
        tool_errors=0,
    )


def test_behavior_hash_ignores_envelopes_but_preserves_payloads_and_order() -> None:
    trace = [
        {"type": "task_start", "timestamp": 1, "input": {"unused": "input"}},
        {
            "type": "tool_call",
            "timestamp": 2,
            "call_id": "a",
            "name": "lookup",
            "args": {"timestamp": 123, "id": "business-id", "nested": {"x": False}},
        },
        {
            "type": "tool_result",
            "timestamp": 3,
            "call_id": "a",
            "ok": True,
            "result": {"timestamp": 456, "value": None},
            "error": None,
        },
        {"type": "final_output", "timestamp": 4, "output": {"answer": "hello", "id": 12}},
    ]
    original = behavior_sha256(_result(trace))
    bookkeeping = copy.deepcopy(trace)
    for event in bookkeeping:
        event.update(timestamp=99, call_id="different", case_id="other")
    bookkeeping.insert(2, {"type": "log", "message": "variable startup logging"})
    assert behavior_sha256(_result(bookkeeping)) == original
    changes = [
        (1, "args", {"timestamp": 124, "id": "business-id", "nested": {"x": False}}),
        (1, "args", {"timestamp": 123, "id": "different-id", "nested": {"x": False}}),
        (1, "args", {"timestamp": 123, "id": "business-id", "nested": {"x": 0}}),
        (2, "result", {"timestamp": 457, "value": None}),
        (2, "ok", False),
        (2, "error", {"code": "different"}),
        (3, "output", {"answer": "hello", "id": 13}),
    ]
    for index, key, value in changes:
        changed = copy.deepcopy(trace)
        changed[index][key] = value
        assert behavior_sha256(_result(changed)) != original, (index, key)
    assert behavior_sha256(_result([trace[0], trace[2], trace[1], trace[3]])) != original


def test_expected_details_use_exact_lists_and_do_not_coerce_booleans() -> None:
    failure = {
        "type": "must_call",
        "message": "missing lookup",
        "details": {"missing": ["lookup"], "nested": {"enabled": False, "extra": 2}},
    }
    result = replace(
        _result([{"type": "assertion_failure", "failures": [failure]}]),
        passed=False,
        failure=Failure(type="assertion_failed", message="missing lookup"),
    )
    assert match_expected_failure(
        result, ExpectedFailure(assertion="must_call", details={"nested": {"enabled": False}})
    )[0]
    for details in (
        {"missing": []},
        {"missing": ["lookup", "other"]},
        {"nested": {"enabled": 0}},
        {"absent": None},
    ):
        assert not match_expected_failure(
            result, ExpectedFailure(assertion="must_call", details=details)
        )[0]


def test_extra_budget_failure_and_assertion_without_output_are_rejected() -> None:
    result = replace(
        _result(
            [
                {
                    "type": "budget_failure",
                    "failures": [
                        {"field": "max_tool_calls", "limit": 1, "actual": 2},
                        {"field": "max_wall_ms", "limit": 10, "actual": 20},
                    ],
                }
            ]
        ),
        passed=False,
        failure=Failure(type="budget_exceeded", message="budget exceeded"),
    )
    assert not match_expected_failure(result, ExpectedFailure(budget="max_tool_calls"))[0]
    assertion = replace(
        result,
        output=None,
        failure=Failure(type="assertion_failed", message="missing lookup"),
        trace=[{"type": "assertion_failure", "failures": [{"type": "must_call"}]}],
    )
    assert not match_expected_failure(assertion, ExpectedFailure(assertion="must_call"))[0]
