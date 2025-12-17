from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import uuid

from runledger import __version__ as runledger_version
from runledger.config.models import SuiteConfig
from runledger.runner.models import CaseResult, SuiteResult


def create_run_dir(base_dir: Path, suite_name: str, run_id: str | None = None) -> tuple[Path, str]:
    if run_id is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_id = f"{timestamp}-{uuid.uuid4().hex[:6]}"
    run_dir = base_dir / suite_name / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, run_id


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        raise ValueError("No values for percentile")
    values_sorted = sorted(values)
    rank = math.ceil((pct / 100.0) * len(values_sorted)) - 1
    rank = max(0, min(rank, len(values_sorted) - 1))
    return values_sorted[rank]


def _metric_summary(values: list[float | int | None]) -> dict[str, float | int | None]:
    numeric = [float(v) for v in values if v is not None]
    if not numeric:
        return {"min": None, "p50": None, "p95": None, "mean": None, "max": None}
    return {
        "min": min(numeric),
        "p50": _percentile(numeric, 50),
        "p95": _percentile(numeric, 95),
        "mean": sum(numeric) / len(numeric),
        "max": max(numeric),
    }


def _case_status(case: CaseResult) -> str:
    if case.passed:
        return "pass"
    if case.failure and case.failure.type in {"agent_error", "cassette_error", "task_error"}:
        return "error"
    return "fail"


def write_summary(
    run_dir: Path,
    *,
    suite: SuiteConfig,
    suite_path: Path,
    suite_result: SuiteResult,
    run_id: str,
) -> Path:
    summary_path = run_dir / "summary.json"
    run_dir.mkdir(parents=True, exist_ok=True)

    cases_list = sorted(suite_result.cases, key=lambda case: case.case_id)
    statuses = [_case_status(case) for case in cases_list]
    cases_total = len(cases_list)
    cases_pass = sum(1 for status in statuses if status == "pass")
    cases_fail = sum(1 for status in statuses if status == "fail")
    cases_error = sum(1 for status in statuses if status == "error")
    pass_rate = (cases_pass / cases_total) if cases_total else 0.0

    metrics = {
        "wall_ms": _metric_summary([case.wall_ms for case in cases_list]),
        "tool_calls": _metric_summary([case.tool_calls for case in cases_list]),
        "tool_errors": _metric_summary([case.tool_errors for case in cases_list]),
        "tokens_in": _metric_summary([case.tokens_in for case in cases_list]),
        "tokens_out": _metric_summary([case.tokens_out for case in cases_list]),
        "cost_usd": _metric_summary([case.cost_usd for case in cases_list]),
        "steps": _metric_summary([case.steps for case in cases_list]),
    }

    exit_status = "success"
    if cases_error:
        exit_status = "error"
    elif cases_fail:
        exit_status = "failed"

    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runledger_version": runledger_version,
        "run": {
            "run_id": run_id,
            "mode": suite.mode,
            "exit_status": exit_status,
            "git_sha": os.getenv("GITHUB_SHA"),
            "ci": None,
        },
        "suite": {
            "name": suite.suite_name,
            "suite_path": str(suite_path),
            "agent_command": suite.agent_command,
            "tool_mode": suite.mode,
            "suite_config_hash": None,
            "cases_total": cases_total,
        },
        "aggregates": {
            "cases_total": cases_total,
            "cases_pass": cases_pass,
            "cases_fail": cases_fail,
            "cases_error": cases_error,
            "pass_rate": pass_rate,
            "metrics": metrics,
        },
        "cases": [
            {
                "id": case.case_id,
                "status": status,
                "wall_ms": case.wall_ms,
                "tool_calls": case.tool_calls,
                "tool_errors": case.tool_errors,
                "tokens_in": case.tokens_in,
                "tokens_out": case.tokens_out,
                "cost_usd": case.cost_usd,
                "steps": case.steps,
                "tool_calls_by_name": case.tool_calls_by_name,
                "tool_errors_by_name": case.tool_errors_by_name,
                "replay": {
                    "cassette_path": case.replay_cassette_path,
                    "cassette_sha256": case.replay_cassette_sha256,
                },
                "assertions": {
                    "total": case.assertions_total,
                    "failed": case.assertions_failed,
                },
                "failure_reason": None if case.failure is None else case.failure.message,
                "failed_assertions": case.failed_assertions,
            }
            for case, status in zip(cases_list, statuses)
        ],
    }

    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path
