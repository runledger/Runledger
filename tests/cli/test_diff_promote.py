from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from runledger.baseline.io import write_baseline
from runledger.baseline.models import BaselineSummary


def _summary_payload(*, pass_rate: float, wall_mean: float, wall_p95: float) -> dict:
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
            "cases_total": 1,
            "cases_pass": 1,
            "cases_fail": 0,
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
                "id": "t1",
                "status": "pass",
                "wall_ms": int(wall_mean),
                "tool_calls": 1,
                "tool_errors": 0,
                "assertions": {"total": 1, "failed": 0},
            }
        ],
    }


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(cwd / "src"))
    return subprocess.run(
        [sys.executable, "-m", "runledger", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
    )


def test_diff_command_reports_failure(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    baseline_payload = _summary_payload(pass_rate=1.0, wall_mean=100.0, wall_p95=100.0)
    run_payload = _summary_payload(pass_rate=1.0, wall_mean=140.0, wall_p95=140.0)
    run_payload["policy_snapshot"] = {
        "thresholds": {"min_pass_rate": 1.0},
        "regression": {
            "max_avg_wall_ms_delta_pct": 0.2,
            "max_p95_wall_ms_delta_pct": 0.2,
        },
    }

    baseline_path = tmp_path / "baseline.json"
    write_baseline(baseline_path, BaselineSummary.model_validate(baseline_payload))

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(run_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        ["diff", "--baseline", str(baseline_path), "--run", str(run_dir)],
        cwd=root,
    )

    assert result.returncode == 1
    assert "Regression Checks" in result.stdout
    assert "FAIL" in result.stdout


def test_baseline_promote_creates_file(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    payload = _summary_payload(pass_rate=1.0, wall_mean=80.0, wall_p95=90.0)
    (run_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    baseline_path = tmp_path / "baseline.json"

    result = _run_cli(
        ["baseline", "promote", "--from", str(run_dir), "--to", str(baseline_path)],
        cwd=root,
    )

    assert result.returncode == 0
    assert baseline_path.is_file()
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
