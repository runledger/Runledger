from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from runledger.artifacts.junit import write_junit
from runledger.artifacts.report import write_report
from runledger.artifacts.run_log import write_run_log
from runledger.artifacts.summary import build_summary, create_run_dir, write_summary
from runledger.baseline.io import load_baseline, write_baseline
from runledger.baseline.models import BaselineSummary
from runledger.config.loader import load_cases, load_suite
from runledger.config.models import RegressionSpec
from runledger.regression import compute_regression
from runledger.runner.engine import run_suite

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
baseline_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(baseline_app, name="baseline")


def _resolve_summary_path(run_path: Path) -> Path:
    if run_path.is_dir():
        summary_path = run_path / "summary.json"
    elif run_path.is_file() and run_path.name == "summary.json":
        summary_path = run_path
    else:
        raise FileNotFoundError(f"Run summary not found at: {run_path}")
    if not summary_path.is_file():
        raise FileNotFoundError(f"Run summary not found at: {summary_path}")
    return summary_path


def _regression_from_policy(policy_snapshot: object) -> RegressionSpec | None:
    if not isinstance(policy_snapshot, dict):
        return None
    payload: dict[str, object] = {}
    thresholds = policy_snapshot.get("thresholds")
    if isinstance(thresholds, dict):
        payload.update(thresholds)
    regression = policy_snapshot.get("regression")
    if isinstance(regression, dict):
        payload.update(regression)
    if not payload:
        return None
    return RegressionSpec.model_validate(payload)


def _print_regression(regression: dict[str, object]) -> None:
    table = Table(title="Regression Checks", show_lines=False)
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Details")

    def _fmt(value: object) -> str:
        if value is None:
            return "n/a"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value)

    for check in regression.get("checks", []):
        status_value = check.get("status")
        if status_value == "pass":
            status = "[green]PASS[/green]"
        elif status_value == "fail":
            status = "[red]FAIL[/red]"
        else:
            status = "[yellow]SKIP[/yellow]"
        threshold = check.get("threshold")
        baseline_value = check.get("baseline")
        current_value = check.get("current")
        delta_pct = check.get("delta_pct")
        delta = check.get("delta")
        details = f"baseline={_fmt(baseline_value)} current={_fmt(current_value)}"
        if delta_pct is not None:
            details = f"{details} delta_pct={_fmt(delta_pct)}"
        elif delta is not None:
            details = f"{details} delta={_fmt(delta)}"
        if threshold is not None:
            details = f"{details} threshold={_fmt(threshold)}"
        note = check.get("note")
        if note:
            details = f"{details} ({note})"
        table.add_row(str(check.get("id")), status, details)
    console.print(table)
    warnings = regression.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning}")


@app.command()
def init(
    path: str = typer.Argument(".", help="Directory to create evals in"),
) -> None:
    """Initialize an example eval suite."""
    console.print(f"[yellow]init[/yellow] is not implemented yet. Target: {path}")


@app.command()
def run(
    suite_dir: str = typer.Argument(
        ...,
        help="Path to a suite directory containing suite.yaml",
    ),
    mode: Optional[str] = typer.Option(
        None,
        help="Run mode (replay, record, live)",
    ),
    output_dir: Optional[str] = typer.Option(
        None,
        help="Output directory override",
    ),
    case: Optional[str] = typer.Option(
        None,
        help="Run a single case by id",
    ),
) -> None:
    """Run a suite against an agent."""
    suite_path = Path(suite_dir)
    suite_dir_path = suite_path if suite_path.is_dir() else suite_path.parent

    try:
        suite = load_suite(suite_path)
    except Exception as exc:
        console.print(f"[red]Failed to load suite:[/red] {exc}")
        raise typer.Exit(code=1)

    if mode is not None:
        if mode not in {"replay", "record", "live"}:
            console.print(f"[red]Unsupported mode:[/red] {mode}")
            raise typer.Exit(code=1)
        suite = suite.model_copy(update={"mode": mode})

    try:
        cases = load_cases(suite_dir_path, suite.cases_path)
    except Exception as exc:
        console.print(f"[red]Failed to load cases:[/red] {exc}")
        raise typer.Exit(code=1)

    if case is not None:
        filtered = [item for item in cases if item.id == case]
        if not filtered:
            console.print(f"[red]Case not found:[/red] {case}")
            raise typer.Exit(code=1)
        cases = filtered

    suite_result = run_suite(suite, cases)
    results = suite_result.cases

    base_dir = Path(output_dir) if output_dir else Path(suite.output_dir or "runledger_out")
    run_dir, run_id = create_run_dir(base_dir, suite.suite_name)
    suite_file_path = suite_path if suite_path.is_file() else suite_path / "suite.yaml"
    generated_at = datetime.now(timezone.utc)

    summary_base = build_summary(
        suite=suite,
        suite_path=suite_file_path,
        suite_result=suite_result,
        run_id=run_id,
        generated_at=generated_at,
    )

    regression = None
    if suite.baseline_path:
        try:
            baseline_path = Path(suite.baseline_path)
            baseline = load_baseline(baseline_path)
            current = BaselineSummary.model_validate(summary_base)
            regression = compute_regression(
                baseline=baseline,
                current=current,
                thresholds=suite.regression,
                baseline_path=baseline_path,
            )
        except Exception as exc:
            console.print(f"[red]Failed to load baseline or compute diff:[/red] {exc}")
            raise typer.Exit(code=1)

    summary_data = build_summary(
        suite=suite,
        suite_path=suite_file_path,
        suite_result=suite_result,
        run_id=run_id,
        regression=regression,
        generated_at=generated_at,
    )

    write_run_log(run_dir, results)
    write_summary(
        run_dir,
        suite=suite,
        suite_path=suite_file_path,
        suite_result=suite_result,
        run_id=run_id,
        regression=regression,
        generated_at=generated_at,
    )
    write_junit(run_dir, suite.suite_name, results)
    write_report(run_dir, summary=summary_data, run_log_path=run_dir / "run.jsonl")

    passed = suite_result.passed and (regression is None or regression.get("passed", True))
    table = Table(title="RunLedger Results", show_lines=False)
    table.add_column("Case")
    table.add_column("Status")
    table.add_column("Wall (ms)", justify="right")
    for result in results:
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        table.add_row(result.case_id, status, str(result.wall_ms))
    console.print(table)
    if regression is not None:
        _print_regression(regression)
    console.print(f"Artifacts written to: {run_dir}")

    raise typer.Exit(code=0 if passed else 1)


@app.command()
def diff(
    baseline: str = typer.Option(..., "--baseline", help="Path to the baseline summary.json"),
    run: str = typer.Option(..., "--run", help="Run directory or summary.json to compare"),
) -> None:
    """Compare a run summary against a baseline and report regressions."""
    baseline_path = Path(baseline)
    run_path = Path(run)
    try:
        baseline_summary = load_baseline(baseline_path)
        summary_path = _resolve_summary_path(run_path)
        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
        current_summary = BaselineSummary.model_validate(summary_data)
    except Exception as exc:
        console.print(f"[red]Failed to load baseline or run summary:[/red] {exc}")
        raise typer.Exit(code=1)

    thresholds = _regression_from_policy(summary_data.get("policy_snapshot"))
    regression = compute_regression(
        baseline=baseline_summary,
        current=current_summary,
        thresholds=thresholds,
        baseline_path=baseline_path,
    )
    _print_regression(regression)

    raise typer.Exit(code=0 if regression.get("passed", True) else 1)


@baseline_app.command("promote")
def promote(
    source: str = typer.Option(
        ...,
        "--from",
        help="Run directory or summary.json to promote",
    ),
    destination: str = typer.Option(
        ...,
        "--to",
        help="Destination baseline path",
    ),
) -> None:
    """Promote a run summary to a baseline file."""
    run_path = Path(source)
    baseline_path = Path(destination)
    try:
        summary_path = _resolve_summary_path(run_path)
        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
        baseline = BaselineSummary.model_validate(summary_data)
        write_baseline(baseline_path, baseline)
    except Exception as exc:
        console.print(f"[red]Failed to promote baseline:[/red] {exc}")
        raise typer.Exit(code=1)
    console.print(f"Baseline written to: {baseline_path}")
