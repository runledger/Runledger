"""Local-only production incident commands; no hosted uploads or embedded code."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from runledger.scenarios.cli import _command, _prepare_output_directory

from .artifacts import write_artifacts
from .importer import import_incident, read_bundle, write_json
from .replay import evaluate_incident, replay_incident
from .schema import read_json


def parser(prog: str) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog=prog, description="Import, redact, review, and replay production incident exports locally.")
    commands = result.add_subparsers(dest="action", required=True)
    ingest = commands.add_parser("import", help="Validate and redact a local production export; never copies the raw source")
    ingest.add_argument("source")
    ingest.add_argument("--format", choices=("canonical", "runledger"), default="canonical")
    ingest.add_argument("--case", help="One case_id from a RunLedger JSONL log")
    ingest.add_argument("--rules", help="JSON file containing an explicit assertion array (required for JSONL)")
    ingest.add_argument("--redact", action="append", default=[], help="Additional JSON Pointer to redact; * matches one level, e.g. /input/company")
    ingest.add_argument("--effects-complete", action="store_true", help="JSONL only: declare that its audit ledger captures every relevant committed effect")
    ingest.add_argument("--out", required=True, help="New or empty output directory")
    for action in ("inspect", "replay"):
        cmd = commands.add_parser(action, help="Evaluate recorded evidence" if action == "inspect" else "Rerun an explicit local JSONL agent with ordered recorded tool responses")
        cmd.add_argument("bundle")
        cmd.add_argument("--out", required=True, help="New or empty output directory")
        cmd.add_argument("--gate", action="store_true", help="Exit 1 if business rules fail/inconclusive, even if the incident reproduces")
        if action == "replay":
            cmd.add_argument("--agent-command", required=True, help="Trusted local command as JSON array; bundle commands are never executed")
    promote = commands.add_parser("promote", help="Save the validated sanitized bundle as a regression fixture without overwriting")
    promote.add_argument("bundle")
    promote.add_argument("--to", required=True)
    return result


def main(argv: list[str] | None = None, *, prog: str = "runledger incident") -> int:
    args = parser(prog).parse_args(argv)
    try:
        if args.action == "import":
            if args.format == "canonical" and (args.case is not None or args.effects_complete):
                raise ValueError("--case and --effects-complete apply only to RunLedger JSONL exports")
            rules = read_json(Path(args.rules)) if args.rules else None
            bundle = import_incident(Path(args.source), format=args.format, case=args.case, rules=rules,
                                     extra_paths=args.redact, effects_complete=args.effects_complete)
        else:
            bundle = read_bundle(Path(args.bundle))
        if args.action == "promote":
            write_json(Path(args.to), bundle)
            print("Sanitized regression fixture saved. Replay with your explicit --agent-command and --gate.")
            return 0
        command = _command(args.agent_command) if args.action == "replay" else None
        directory = Path(args.out)
        _prepare_output_directory(directory)
        replay = replay_incident(bundle["incident"], command) if command else None
        evaluation = replay["observed"] if replay else evaluate_incident(bundle["incident"])
        write_artifacts(directory, bundle, evaluation, replay)
        if args.action == "import":
            print("Imported and redacted locally. Review report.html and incident.json before sharing.")
            print("The raw source, redaction key, and value lookup table were not exported.")
        if replay is not None:
            print("Agent replay: " + ("MATCHED" if replay["matched"] else "DIVERGED / AGENT ERROR"))
        print("Business rules: " + ("PASS" if evaluation["passed"] else "FAIL / INCONCLUSIVE"))
        print("Artifacts: " + str(directory.resolve()))
        if replay is not None and not replay["matched"]:
            return 1
        if getattr(args, "gate", False) and not evaluation["passed"]:
            return 1
        return 0
    except (ValueError, KeyError, TypeError, OSError, ImportError, RecursionError) as exc:
        # Safe validator messages may explain shape; never echo raw JSON, agent
        # stderr, arguments, or exception diagnostics containing customer values.
        from .redaction import RedactionError
        from .schema import IncidentError
        if isinstance(exc, (IncidentError, RedactionError)):
            message = str(exc)
        elif isinstance(exc, FileExistsError):
            message = "Output exists; choose a fresh path. Existing evidence was not overwritten."
        else:
            message = "Invalid input, command, or output location. Check --help and use a new output directory."
        print("Error: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
