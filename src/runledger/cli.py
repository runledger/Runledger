from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

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
    _ = (mode, output_dir, case)
    console.print("[yellow]run[/yellow] is not implemented yet.")
    raise typer.Exit(code=1)
