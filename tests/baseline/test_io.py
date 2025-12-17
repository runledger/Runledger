from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from runledger.baseline.io import load_baseline, write_baseline
from runledger.baseline.models import BaselineSummary


def _baseline_payload() -> dict:
    return {
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
            "cases_total": 2,
            "cases_pass": 2,
            "cases_fail": 0,
            "cases_error": 0,
            "pass_rate": 1.0,
            "metrics": {
                "wall_ms": {"min": 1, "p50": 1, "p95": 1, "mean": 1, "max": 1}
            },
        },
        "cases": [
            {
                "id": "b",
                "status": "pass",
                "wall_ms": 1,
                "tool_calls": 1,
                "tool_errors": 0,
                "assertions": {"total": 1, "failed": 0},
            },
            {
                "id": "a",
                "status": "pass",
                "wall_ms": 1,
                "tool_calls": 1,
                "tool_errors": 0,
                "assertions": {"total": 1, "failed": 0},
            },
        ],
    }


def test_write_and_load_baseline(tmp_path: Path) -> None:
    baseline = BaselineSummary.model_validate(_baseline_payload())
    baseline_path = tmp_path / "baseline.json"

    write_baseline(baseline_path, baseline)
    loaded = load_baseline(baseline_path)

    assert loaded.suite.name == "demo"
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert [case["id"] for case in data["cases"]] == ["a", "b"]
