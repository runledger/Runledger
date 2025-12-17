from __future__ import annotations

from datetime import datetime, timezone
import json
import shutil
from pathlib import Path
from typing import Optional

import typer
import yaml
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
    path: str = typer.Option(
        "./evals",
        "--path",
        help="Directory to create evals in",
    ),
    suite: str = typer.Option("demo", help="Suite name to generate"),
    template: str = typer.Option("support-triage", help="Template name"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing suite files"),
    language: str = typer.Option("python", help="Agent language (python only in v0.1)"),
) -> None:
    """Initialize an example eval suite."""
    if template != "support-triage":
        console.print(f"[red]Unknown template:[/red] {template}")
        raise typer.Exit(code=1)
    if language != "python":
        console.print(f"[red]Unsupported language:[/red] {language}")
        raise typer.Exit(code=1)

    base_dir = Path(path).resolve()
    evals_dir = base_dir / suite
    cases_dir = evals_dir / "cases"
    cassettes_dir = evals_dir / "cassettes"
    agent_dir = evals_dir / "agent"
    baselines_dir = base_dir.parent / "baselines"
    agent_path = agent_dir / "agent.py"

    if evals_dir.exists():
        if not force:
            console.print(f"[red]Target already exists:[/red] {evals_dir}")
            raise typer.Exit(code=1)
        shutil.rmtree(evals_dir)
    if baselines_dir.exists():
        baseline_file = baselines_dir / f"{suite}.json"
        if baseline_file.exists() and force:
            baseline_file.unlink()

    agent_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(parents=True, exist_ok=True)
    cassettes_dir.mkdir(parents=True, exist_ok=True)
    baselines_dir.mkdir(parents=True, exist_ok=True)

    agent_path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "",
                "def send(payload):",
                "    sys.stdout.write(json.dumps(payload) + \"\\n\")",
                "    sys.stdout.flush()",
                "",
                "for line in sys.stdin:",
                "    line = line.strip()",
                "    if not line:",
                "        continue",
                "    msg = json.loads(line)",
                "    if msg.get(\"type\") == \"task_start\":",
                "        ticket = msg.get(\"input\", {}).get(\"ticket\", \"\")",
                "        send({\"type\": \"tool_call\", \"name\": \"search_docs\", \"call_id\": \"c1\", \"args\": {\"q\": ticket}})",
                "    elif msg.get(\"type\") == \"tool_result\":",
                "        send({\"type\": \"final_output\", \"output\": {\"category\": \"account\", \"reply\": \"Reset password instructions sent.\"}})",
                "        break",
                "",
            ]
        ),
        encoding="utf-8",
    )

    schema_path = evals_dir / "schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "reply": {"type": "string"},
                },
                "required": ["category", "reply"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    cassette_path = cassettes_dir / "t1.jsonl"
    cassette_path.write_text(
        json.dumps(
            {
                "tool": "search_docs",
                "args": {"q": "reset password"},
                "ok": True,
                "result": {"hits": [{"title": "Reset password", "snippet": "Use the reset link."}]},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    case_path = cases_dir / "t1.yaml"
    case_path.write_text(
        yaml.safe_dump(
            {
                "id": "t1",
                "description": "triage a login ticket",
                "input": {"ticket": "reset password"},
                "cassette": "cassettes/t1.jsonl",
                "assertions": [
                    {"type": "required_fields", "fields": ["category", "reply"]},
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    suite_path = evals_dir / "suite.yaml"
    suite_path.write_text(
        yaml.safe_dump(
            {
                "suite_name": suite,
                "agent_command": ["python", "agent/agent.py"],
                "mode": "replay",
                "cases_path": "cases",
                "tool_registry": ["search_docs"],
                "assertions": [
                    {"type": "json_schema", "schema_path": "schema.json"},
                ],
                "budgets": {
                    "max_wall_ms": 20000,
                    "max_tool_calls": 1,
                    "max_tool_errors": 0,
                },
                "regression": {
                    "min_pass_rate": 1.0,
                },
                "baseline_path": f"../../baselines/{suite}.json",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    try:
        suite_config = load_suite(suite_path)
        cases = load_cases(evals_dir, suite_config.cases_path)
        suite_run = suite_config.model_copy(
            update={"agent_command": ["python", str(agent_path)]}
        )
        suite_result = run_suite(suite_run, cases)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        summary = build_summary(
            suite=suite_config,
            suite_path=suite_path,
            suite_result=suite_result,
            run_id=run_id,
            generated_at=datetime.now(timezone.utc),
        )
        baseline = BaselineSummary.model_validate(summary)
        write_baseline(baselines_dir / f"{suite}.json", baseline)
    except Exception as exc:
        console.print(f"[red]Failed to generate baseline:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print(f"Created eval suite at: {evals_dir}")
    console.print(f"Created baseline at: {baselines_dir / f'{suite}.json'}")
    console.print("")
    console.print("Next steps:")
    console.print(
        f"  runledger run {evals_dir} --mode replay --baseline {baselines_dir / f'{suite}.json'}"
    )
    console.print(f"  open runledger_out/{suite}/<run_id>/report.html")
    console.print("")
    console.print("GitHub Actions snippet:")
    console.print(
        "\n".join(
            [
                "name: runledger-evals",
                "on:",
                "  pull_request:",
                "",
                "jobs:",
                "  evals:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - uses: actions/checkout@v4",
                "      - name: Install RunLedger",
                "        run: |",
                "          python -m pip install --upgrade pip",
                "          python -m pip install runledger",
                "      - name: Run deterministic evals",
                f"        run: runledger run {evals_dir} --mode replay",
                "      - name: Upload artifacts",
                "        uses: actions/upload-artifact@v4",
                "        with:",
                "          name: runledger-artifacts",
                "          path: runledger_out/**",
            ]
        )
    )


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
    baseline: Optional[str] = typer.Option(
        None,
        help="Baseline path override",
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
    baseline_path = (
        Path(baseline)
        if baseline
        else (Path(suite.baseline_path) if suite.baseline_path else None)
    )
    if baseline_path:
        try:
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
