from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

from runledger.artifacts.junit import write_junit
from runledger.artifacts.run_log import write_run_log
from runledger.artifacts.summary import create_run_dir, write_summary
from runledger.config.models import SuiteConfig
from runledger.runner.models import CaseResult, Failure, SuiteResult


def _case_result(case_id: str, passed: bool) -> CaseResult:
    failure = None
    if not passed:
        failure = Failure(type="assertion_failed", message="missing field")
    return CaseResult(
        case_id=case_id,
        passed=passed,
        output={"status": "ok"} if passed else None,
        trace=[
            {"type": "task_start", "case_id": case_id, "timestamp": 0.0},
            {"type": "case_end", "case_id": case_id, "timestamp": 0.1, "passed": passed},
        ],
        wall_ms=123,
        tool_calls=1,
        tool_errors=0,
        failure=failure,
    )


def test_write_run_log(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    cases = [_case_result("c1", True)]

    run_path = write_run_log(run_dir, cases)
    lines = run_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["type"] == "task_start"
    assert first["case_id"] == "c1"


def test_write_summary_and_junit(tmp_path: Path) -> None:
    base_dir = tmp_path / "runs"
    run_dir, run_id = create_run_dir(base_dir, "demo", run_id="test-run")
    cases = [_case_result("c1", True), _case_result("c2", False)]
    suite = SuiteConfig(
        suite_name="demo",
        agent_command=["python", "agent.py"],
        mode="replay",
        cases_path="cases",
        tool_registry=["search_docs"],
    )
    suite_result = SuiteResult(
        suite_name="demo",
        cases=cases,
        passed=False,
        total_cases=2,
        passed_cases=1,
        failed_cases=1,
        success_rate=0.5,
        total_tool_calls=2,
        total_tool_errors=0,
        total_wall_ms=246,
    )

    summary_path = write_summary(
        run_dir,
        suite=suite,
        suite_path=tmp_path / "suite.yaml",
        suite_result=suite_result,
        run_id=run_id,
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["schema_version"] == 1
    assert summary["suite"]["name"] == "demo"
    assert summary["aggregates"]["cases_total"] == 2
    assert summary["aggregates"]["cases_pass"] == 1
    assert summary["aggregates"]["cases_fail"] == 1

    junit_path = write_junit(run_dir, "demo", cases)
    root = ET.fromstring(junit_path.read_text(encoding="utf-8"))

    assert root.attrib["name"] == "demo"
    assert root.attrib["tests"] == "2"
    assert root.attrib["failures"] == "1"
    failures = root.findall(".//failure")
    assert failures
