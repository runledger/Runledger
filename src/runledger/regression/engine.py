from __future__ import annotations

from pathlib import Path
from typing import Any

from runledger.baseline.models import BaselineSummary
from runledger.config.models import RegressionSpec


def _delta_pct(baseline: float | None, current: float | None) -> float | None:
    if baseline is None or current is None or baseline == 0:
        return None
    return (current - baseline) / baseline


def _metric_value(summary: BaselineSummary, metric: str, field: str) -> float | None:
    metric_summary = summary.aggregates.metrics.get(metric)
    if metric_summary is None:
        return None
    return getattr(metric_summary, field, None)


def compute_regression(
    *,
    baseline: BaselineSummary,
    current: BaselineSummary,
    thresholds: RegressionSpec | None,
    baseline_path: Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    if baseline.schema_version != current.schema_version:
        warnings.append(
            "Baseline schema_version does not match current summary schema_version."
        )

    baseline_cases = {case.id: case for case in baseline.cases}
    current_cases = {case.id: case for case in current.cases}
    missing_cases = sorted(set(baseline_cases) - set(current_cases))
    new_cases = sorted(set(current_cases) - set(baseline_cases))
    status_changed = []
    for case_id in sorted(set(baseline_cases) & set(current_cases)):
        baseline_status = baseline_cases[case_id].status
        current_status = current_cases[case_id].status
        if baseline_status != current_status:
            status_changed.append(
                {"id": case_id, "baseline": baseline_status, "current": current_status}
            )

    baseline_pass_rate = baseline.aggregates.pass_rate
    current_pass_rate = current.aggregates.pass_rate
    baseline_wall_mean = _metric_value(baseline, "wall_ms", "mean")
    current_wall_mean = _metric_value(current, "wall_ms", "mean")
    baseline_wall_p95 = _metric_value(baseline, "wall_ms", "p95")
    current_wall_p95 = _metric_value(current, "wall_ms", "p95")

    checks: list[dict[str, Any]] = []
    passed = True

    def add_check(check: dict[str, Any]) -> None:
        nonlocal passed
        if check["status"] == "fail":
            passed = False
        checks.append(check)

    min_pass_rate = thresholds.min_pass_rate if thresholds else None
    if min_pass_rate is None:
        add_check(
            {
                "id": "min_pass_rate",
                "status": "skipped",
                "threshold": None,
                "baseline": baseline_pass_rate,
                "current": current_pass_rate,
                "delta": current_pass_rate - baseline_pass_rate,
                "note": "No min_pass_rate configured.",
            }
        )
    else:
        add_check(
            {
                "id": "min_pass_rate",
                "status": "pass" if current_pass_rate >= min_pass_rate else "fail",
                "threshold": min_pass_rate,
                "baseline": baseline_pass_rate,
                "current": current_pass_rate,
                "delta": current_pass_rate - baseline_pass_rate,
            }
        )

    max_avg_wall_delta = thresholds.max_avg_wall_ms_delta_pct if thresholds else None
    avg_wall_delta_pct = _delta_pct(baseline_wall_mean, current_wall_mean)
    if max_avg_wall_delta is None:
        add_check(
            {
                "id": "max_avg_wall_ms_delta_pct",
                "status": "skipped",
                "threshold": None,
                "baseline": baseline_wall_mean,
                "current": current_wall_mean,
                "delta_pct": avg_wall_delta_pct,
                "note": "No max_avg_wall_ms_delta_pct configured.",
            }
        )
    elif avg_wall_delta_pct is None:
        add_check(
            {
                "id": "max_avg_wall_ms_delta_pct",
                "status": "skipped",
                "threshold": max_avg_wall_delta,
                "baseline": baseline_wall_mean,
                "current": current_wall_mean,
                "delta_pct": None,
                "note": "Baseline metric missing or zero.",
            }
        )
    else:
        add_check(
            {
                "id": "max_avg_wall_ms_delta_pct",
                "status": "pass" if avg_wall_delta_pct <= max_avg_wall_delta else "fail",
                "threshold": max_avg_wall_delta,
                "baseline": baseline_wall_mean,
                "current": current_wall_mean,
                "delta_pct": avg_wall_delta_pct,
            }
        )

    max_p95_wall_delta = thresholds.max_p95_wall_ms_delta_pct if thresholds else None
    p95_wall_delta_pct = _delta_pct(baseline_wall_p95, current_wall_p95)
    if max_p95_wall_delta is None:
        add_check(
            {
                "id": "max_p95_wall_ms_delta_pct",
                "status": "skipped",
                "threshold": None,
                "baseline": baseline_wall_p95,
                "current": current_wall_p95,
                "delta_pct": p95_wall_delta_pct,
                "note": "No max_p95_wall_ms_delta_pct configured.",
            }
        )
    elif p95_wall_delta_pct is None:
        add_check(
            {
                "id": "max_p95_wall_ms_delta_pct",
                "status": "skipped",
                "threshold": max_p95_wall_delta,
                "baseline": baseline_wall_p95,
                "current": current_wall_p95,
                "delta_pct": None,
                "note": "Baseline metric missing or zero.",
            }
        )
    else:
        add_check(
            {
                "id": "max_p95_wall_ms_delta_pct",
                "status": "pass" if p95_wall_delta_pct <= max_p95_wall_delta else "fail",
                "threshold": max_p95_wall_delta,
                "baseline": baseline_wall_p95,
                "current": current_wall_p95,
                "delta_pct": p95_wall_delta_pct,
            }
        )

    metrics = {
        "pass_rate": {
            "baseline": baseline_pass_rate,
            "current": current_pass_rate,
            "delta": current_pass_rate - baseline_pass_rate,
        },
        "wall_ms": {
            "mean": {
                "baseline": baseline_wall_mean,
                "current": current_wall_mean,
                "delta_pct": avg_wall_delta_pct,
            },
            "p95": {
                "baseline": baseline_wall_p95,
                "current": current_wall_p95,
                "delta_pct": p95_wall_delta_pct,
            },
        },
    }

    return {
        "baseline_path": str(baseline_path),
        "passed": passed,
        "checks": checks,
        "metrics": metrics,
        "case_diffs": {
            "missing_in_current": missing_cases,
            "new_in_current": new_cases,
            "status_changed": status_changed,
        },
        "warnings": warnings,
    }
