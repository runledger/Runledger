from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from runledger.baseline.models import BaselineSummary
from runledger.config.models import RegressionSpec
from runledger.regression import compute_regression


def _summary(
    *,
    pass_rate: float,
    wall_mean: float,
    wall_p95: float,
    case_status: str = "pass",
    case_id: str = "t1",
) -> BaselineSummary:
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runledger_version": "0.1.0",
        "run": {"run_id": "run-1", "mode": "replay", "exit_status": "success"},
        "suite": {
            "name": "demo",
            "suite_path": "suite.yaml",
            "agent_command": ["python", "agent.py"],
            "tool_mode": "replay",
        },
        "aggregates": {
            "cases_total": 1,
            "cases_pass": 1 if case_status == "pass" else 0,
            "cases_fail": 0 if case_status == "pass" else 1,
            "cases_error": 0,
            "pass_rate": pass_rate,
            "metrics": {
                "wall_ms": {
                    "min": wall_mean,
                    "p50": wall_mean,
                    "p95": wall_p95,
                    "mean": wall_mean,
                    "max": wall_p95,
                }
            },
        },
        "cases": [
            {
                "id": case_id,
                "status": case_status,
                "wall_ms": int(wall_mean),
                "tool_calls": 1,
                "tool_errors": 0,
                "assertions": {"total": 1, "failed": 0},
            }
        ],
    }
    return BaselineSummary.model_validate(payload)


def test_regression_checks_and_case_diffs() -> None:
    baseline = _summary(pass_rate=1.0, wall_mean=1000, wall_p95=1500, case_id="t1")
    current = _summary(pass_rate=0.8, wall_mean=1200, wall_p95=2000, case_id="t2")
    thresholds = RegressionSpec(
        min_pass_rate=0.9,
        max_avg_wall_ms_delta_pct=0.1,
        max_p95_wall_ms_delta_pct=0.2,
    )

    result = compute_regression(
        baseline=baseline,
        current=current,
        thresholds=thresholds,
        baseline_path=Path("baselines/demo.json"),
    )

    assert result["passed"] is False
    check_status = {check["id"]: check["status"] for check in result["checks"]}
    assert check_status["min_pass_rate"] == "fail"
    assert check_status["max_avg_wall_ms_delta_pct"] == "fail"
    assert check_status["max_p95_wall_ms_delta_pct"] == "fail"
    assert result["case_diffs"]["missing_in_current"] == ["t1"]
    assert result["case_diffs"]["new_in_current"] == ["t2"]
