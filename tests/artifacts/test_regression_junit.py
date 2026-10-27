from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from runledger import cli
from runledger.artifacts.junit import write_junit
from runledger.artifacts.summary import build_summary
from runledger.config.models import SuiteConfig
from runledger.runner.models import CaseResult, Failure, SuiteResult


def _case() -> CaseResult:
    return CaseResult(
        case_id="c1", passed=True, output={}, trace=[], wall_ms=100, tool_calls=0, tool_errors=0
    )


def _suite_result(case: CaseResult) -> SuiteResult:
    return SuiteResult(
        suite_name="demo",
        cases=[case],
        passed=True,
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        success_rate=1.0,
        total_tool_calls=0,
        total_tool_errors=0,
        total_wall_ms=case.wall_ms,
    )


def test_junit_includes_each_failed_gate_without_changing_case_results(tmp_path: Path) -> None:
    regression = {
        "passed": False,
        "checks": [
            {"id": "min_pass_rate", "status": "pass"},
            {"id": "unused", "status": "skipped"},
            {
                "id": "max_avg_wall_ms_delta_pct",
                "status": "fail",
                "threshold": 0.2,
                "baseline": 50,
                "current": 100,
                "delta_pct": 1.0,
            },
            {
                "id": "max_p95_wall_ms_delta_pct",
                "status": "fail",
                "threshold": 0.2,
                "baseline": 50,
                "current": 100,
                "delta_pct": 1.0,
            },
        ],
    }
    path = write_junit(tmp_path, "demo", [_case()], regression=regression)
    suite = ET.parse(path).getroot()
    assert suite.get("tests") == "3"
    assert suite.get("failures") == "2"
    assert suite.get("time") == "0.100"
    assert suite.find("testcase[@name='c1']/failure") is None
    gates = suite.findall("testcase[@classname='runledger.regression']")
    assert {gate.get("name") for gate in gates} == {
        "regression:max_avg_wall_ms_delta_pct",
        "regression:max_p95_wall_ms_delta_pct",
    }
    for gate in gates:
        failure = gate.find("failure")
        assert failure is not None
        assert failure.get("type") == "regression"
        assert "baseline 50, current 100" in failure.get("message", "")
        assert "allowed 0.2000" in (failure.text or "")


def test_junit_redacts_secrets_in_failure_messages(tmp_path: Path) -> None:
    secret = "ghp_" + "a" * 36
    case = replace(
        _case(),
        passed=False,
        failure=Failure(type="task_error", message=f"Authorization: Bearer abc.def.ghi; {secret}"),
    )
    path = write_junit(tmp_path, "demo", [case])
    content = path.read_text(encoding="utf-8")
    assert "abc.def.ghi" not in content
    assert secret not in content
    failure = ET.parse(path).getroot().find("testcase/failure")
    assert failure is not None
    assert failure.get("message") == "Authorization: Bearer [REDACTED]; [REDACTED]"


def test_cli_regression_failure_agrees_with_junit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite = SuiteConfig(
        suite_name="demo",
        agent_command=["unused"],
        mode="replay",
        cases_path="cases",
        tool_registry=[],
        regression={"max_p95_wall_ms_delta_pct": 0.2},
    )
    (tmp_path / "suite.yaml").write_text(yaml.safe_dump(suite.model_dump()), encoding="utf-8")
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "c1.yaml").write_text(
        yaml.safe_dump({"id": "c1", "input": {}, "cassette": "unused.jsonl"}), encoding="utf-8"
    )
    baseline = build_summary(
        suite=suite,
        suite_path=tmp_path / "suite.yaml",
        run_id="baseline",
        suite_result=_suite_result(replace(_case(), wall_ms=10)),
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    monkeypatch.setattr(cli, "run_suite", lambda *_args: _suite_result(_case()))
    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            str(tmp_path),
            "--baseline",
            str(baseline_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 1, result.output
    summary_path = next((tmp_path / "out").rglob("summary.json"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["cases"][0]["status"] == "pass"
    assert summary["run"]["exit_status"] == "failed"
    assert summary["regression"]["passed"] is False
    junit = ET.parse(summary_path.with_name("junit.xml")).getroot()
    assert junit.get("tests") == "2"
    assert junit.get("failures") == "1"
    assert junit.find("testcase[@name='c1']/failure") is None
    assert junit.find("testcase[@name='regression:max_p95_wall_ms_delta_pct']/failure") is not None
