from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from runledger.runner.models import CaseResult


def create_run_dir(base_dir: Path, suite_name: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = base_dir / suite_name / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_summary(run_dir: Path, suite_name: str, cases: Iterable[CaseResult]) -> Path:
    summary_path = run_dir / "summary.json"
    run_dir.mkdir(parents=True, exist_ok=True)

    cases_list = list(cases)
    total = len(cases_list)
    passed = sum(1 for case in cases_list if case.passed)
    failed = total - passed
    success_rate = (passed / total) if total else 0.0

    summary = {
        "suite_name": suite_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": total,
        "passed": passed,
        "failed": failed,
        "success_rate": success_rate,
        "cases": [
            {
                "id": case.case_id,
                "passed": case.passed,
                "wall_ms": case.wall_ms,
                "tool_calls": case.tool_calls,
                "tool_errors": case.tool_errors,
                "failure": None
                if case.failure is None
                else {"type": case.failure.type, "message": case.failure.message},
            }
            for case in cases_list
        ],
    }

    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary_path
