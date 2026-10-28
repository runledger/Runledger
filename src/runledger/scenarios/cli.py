"""The same stdlib command line powers the downloadable pack and RunLedger."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bundles import read_bundle, reproduce_bundle, write_bundle
from .core import run_scenario, validate_spec
from .pack import get_scenario, scenarios
from .reports import compare_runs, write_json, write_junit, write_report, write_run_artifacts


def verify_scenarios(selected: list[dict], command: list[str] | None = None) -> list[dict]:
    results = []
    for spec in selected:
        before = run_scenario(spec, agent="unsafe")
        after = run_scenario(spec, agent="fixed", command=command)
        results.append({"id": spec["id"], "title": spec["title"], "description": spec["description"],
                        "before": before, "after": after, "comparison": compare_runs(before, after)})
    return results


def _command(value: str | None) -> list[str] | None:
    if value is None:
        return None
    command = json.loads(value)
    if not isinstance(command, list) or not command or not all(isinstance(v, str) and v for v in command):
        raise ValueError("--agent-command must be a JSON array, e.g. '[\"python\", \"agent.py\"]'")
    return command


def _selected(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "case", None):
        path = Path(args.case)
        if path.stat().st_size > 100_000:
            raise ValueError("Regression case is too large")
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or set(data) != {"schema_version", "scenario"}
                or type(data["schema_version"]) is not int or data["schema_version"] != 1):
            raise ValueError("Unsupported regression case")
        return [validate_spec(data["scenario"])]
    if args.scenario == "all":
        return scenarios()
    return [get_scenario(args.scenario)]


def _prepare_output_directory(directory: Path) -> None:
    """Keep one invocation's evidence separate from earlier or custom runs."""
    if directory.is_symlink():
        raise ValueError("Output directory must not be a symbolic link")
    if directory.exists():
        if not directory.is_dir() or any(directory.iterdir()):
            raise ValueError(
                "Output directory already contains files; choose a new or empty --out directory. "
                "Existing evidence was not changed."
            )
    else:
        directory.mkdir(parents=True)


def parser(prog: str) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog=prog, description="Support-agent scenario pack v1: simulated actions, real pass/fail evidence.")
    commands = result.add_subparsers(dest="action", required=True)
    commands.add_parser("list", help="List five synthetic support-agent scenarios")
    for action in ("run", "verify"):
        cmd = commands.add_parser(action, help="Run business-rule checks" if action == "run" else "Compare unsafe and candidate policies")
        selection = cmd.add_mutually_exclusive_group()
        selection.add_argument("--scenario", default="all", help="Scenario ID or all (default)")
        selection.add_argument("--case", help="A promoted regression case JSON file")
        if action == "run":
            cmd.add_argument("--agent", choices=("unsafe", "fixed"), default="fixed")
        cmd.add_argument("--agent-command", help="Full installed CLI only: explicit trusted local JSONL command as a JSON array")
        cmd.add_argument("--out", default="scenario-results", help="New or empty output directory; prior evidence is never overwritten")
    reproduce = commands.add_parser("reproduce", help="Reproduce a synthetic incident; exit 0 means the evidence matches")
    reproduce.add_argument("bundle")
    reproduce.add_argument("--out", default="reproduced")
    promote = commands.add_parser("promote", help="Turn a validated incident scenario into a reusable regression case")
    promote.add_argument("bundle")
    promote.add_argument("--to", required=True, help="New case JSON path; will not overwrite")
    return result


def main(argv: list[str] | None = None, *, prog: str = "python run_demo.py") -> int:
    args = parser(prog).parse_args(argv)
    try:
        if args.action == "list":
            for spec in scenarios():
                print(spec["id"] + "  " + spec["title"])
            return 0
        if args.action == "promote":
            bundle = read_bundle(Path(args.bundle))
            target = Path(args.to)
            if target.exists():
                raise ValueError("Refusing to overwrite an existing regression case")
            target.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive create also prevents a race from overwriting a file.
            with target.open("x", encoding="utf-8") as stream:
                json.dump({"schema_version": 1, "scenario": bundle["scenario"]}, stream, indent=2)
                stream.write("\n")
            print("Regression case written to " + str(target))
            print(f'{prog} run --case "{target}" --agent fixed --out regression-results')
            return 0
        directory = Path(args.out)
        if args.action == "reproduce":
            reproduced = reproduce_bundle(Path(args.bundle))
            _prepare_output_directory(directory)
            write_run_artifacts(directory, reproduced["result"])
            write_json(directory / "reproduction.json", reproduced)
            print("Evidence " + ("MATCHED" if reproduced["matched"] else "DIVERGED") + "; reproduced scenario "
                  + ("PASS" if reproduced["result"]["passed"] else "FAIL"))
            print("Artifacts: " + str(directory.resolve()))
            return 0 if reproduced["matched"] else 1
        command = _command(args.agent_command)
        selected = _selected(args)
        _prepare_output_directory(directory)
        if args.action == "verify":
            comparisons = verify_scenarios(selected, command)
            write_json(directory / "comparison.json", {"schema_version": 1, "scenarios": comparisons})
            write_report(directory / "report.html", comparisons=comparisons)
            write_junit(directory / "junit.xml", [item["after"] for item in comparisons])
            for spec, item in zip(selected, comparisons):
                for key in ("before", "after"):
                    target = directory / spec["id"] / key
                    write_run_artifacts(target, item[key])
                    if key == "before" or command is None:
                        write_bundle(target / "incident.json", spec, item[key])
                print(spec["id"] + ": " + ("FAIL" if not item["before"]["passed"] else "PASS")
                      + " -> " + ("PASS" if item["after"]["passed"] else "FAIL")
                      + f' ({item["comparison"]["before_refunds"]} -> {item["comparison"]["after_refunds"]} refunds)')
            passed = all(item["comparison"]["verified"] for item in comparisons)
        else:
            runs = []
            for spec in selected:
                run = run_scenario(spec, agent=args.agent, command=command)
                target = directory if len(selected) == 1 else directory / spec["id"]
                write_run_artifacts(target, run)
                if command is None:
                    write_bundle(target / "incident.json", spec, run)
                runs.append(run)
                print(spec["id"] + ": " + ("PASS" if run["passed"] else "FAIL"))
            if len(selected) > 1:
                write_report(directory / "report.html", runs=runs)
                write_junit(directory / "junit.xml", runs)
            passed = all(run["passed"] for run in runs)
        print("Artifacts: " + str(directory.resolve()))
        if command:
            print("Custom-agent artifacts remain local and may contain sensitive data; no portable bundle was exported for the custom agent.")
        return 0 if passed else 1
    except (ValueError, KeyError, TypeError, OSError, ImportError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
