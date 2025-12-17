from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from runledger.artifacts.junit import write_junit
from runledger.artifacts.run_log import write_run_log
from runledger.artifacts.summary import create_run_dir, write_summary
from runledger.config.loader import load_cases, load_suite
from runledger.runner.engine import run_suite

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


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

    if mode is not None and mode != "replay":
        console.print("[red]Only replay mode is supported in the MVP.[/red]")
        raise typer.Exit(code=1)

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
    write_run_log(run_dir, results)
    write_summary(
        run_dir,
        suite=suite,
        suite_path=(suite_path if suite_path.is_file() else suite_path / "suite.yaml"),
        suite_result=suite_result,
        run_id=run_id,
    )
    write_junit(run_dir, suite.suite_name, results)

    passed = suite_result.passed
    table = Table(title="RunLedger Results", show_lines=False)
    table.add_column("Case")
    table.add_column("Status")
    table.add_column("Wall (ms)", justify="right")
    for result in results:
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        table.add_row(result.case_id, status, str(result.wall_ms))
    console.print(table)
    console.print(f"Artifacts written to: {run_dir}")

    raise typer.Exit(code=0 if passed else 1)
