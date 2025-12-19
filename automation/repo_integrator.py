from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil

import json
import yaml

from automation.common import ensure_tool, load_config, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a minimal RunLedger integration patch.")
    parser.add_argument("--config", default="automation/config.yaml", help="Path to config YAML")
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/name form")
    parser.add_argument("--workdir", default=None, help="Workdir base (overrides config)")
    parser.add_argument("--branch", default="runledger/replay-gate", help="Branch name to create")
    parser.add_argument("--skip-baseline", action="store_true", help="Skip baseline generation")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not modify repo")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    ensure_tool("git")
    ensure_tool("runledger", ["--help"])

    workdir = Path(args.workdir or cfg.data.get("output", {}).get("workdir", "automation/workdir"))
    repo_dir = workdir / args.repo.replace("/", "_")
    integration_cfg = cfg.data.get("integration", {})
    suite_name = integration_cfg.get("suite_name", "runledger-demo")
    evals_dir = Path(integration_cfg.get("evals_dir", "evals/runledger"))
    baseline_dir = Path(integration_cfg.get("baseline_dir", "baselines"))
    workflow_path = Path(integration_cfg.get("workflow_path", ".github/workflows/runledger.yml"))
    action_ref = integration_cfg.get("action_ref", "runledger/Runledger@v0.1")
    replay_only = bool(integration_cfg.get("replay_only", True))
    max_diff_lines = int(integration_cfg.get("max_diff_lines", 200))

    if args.dry_run:
        print("Dry run: would clone and prepare patch for", args.repo)
        print("Workdir:", repo_dir)
        print("Suite dir:", evals_dir)
        print("Baseline dir:", baseline_dir)
        print("Workflow:", workflow_path)
        print("Action ref:", action_ref)
        return

    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    workdir.mkdir(parents=True, exist_ok=True)

    run(["git", "clone", f"https://github.com/{args.repo}.git", str(repo_dir)])
    run(["git", "checkout", "-b", args.branch], cwd=repo_dir)

    suite_dir = repo_dir / evals_dir
    cases_dir = suite_dir / "cases"
    cassettes_dir = suite_dir / "cassettes"
    agent_dir = suite_dir / "agent"
    baseline_file = repo_dir / baseline_dir / f"{suite_name}.json"

    cases_dir.mkdir(parents=True, exist_ok=True)
    cassettes_dir.mkdir(parents=True, exist_ok=True)
    agent_dir.mkdir(parents=True, exist_ok=True)
    baseline_file.parent.mkdir(parents=True, exist_ok=True)

    suite_path = suite_dir / "suite.yaml"
    schema_path = suite_dir / "schema.json"
    case_path = cases_dir / "t1.yaml"
    cassette_path = cassettes_dir / "t1.jsonl"
    agent_path = agent_dir / "agent.py"

    suite_yaml = {
        "suite_name": suite_name,
        "agent_command": ["python", "agent/agent.py"],
        "mode": "replay" if replay_only else "record",
        "cases_path": "cases",
        "tool_registry": ["search_docs"],
        "assertions": [{"type": "json_schema", "schema_path": "schema.json"}],
        "budgets": {"max_wall_ms": 20000, "max_tool_calls": 1, "max_tool_errors": 0},
        "regression": {"min_pass_rate": 1.0},
        "baseline_path": _relpath(baseline_file, suite_dir),
    }
    suite_path.write_text(yaml.safe_dump(suite_yaml, sort_keys=False), encoding="utf-8")

    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"category": {"type": "string"}, "reply": {"type": "string"}},
                "required": ["category", "reply"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    case_path.write_text(
        yaml.safe_dump(
            {
                "id": "t1",
                "description": "triage a login ticket",
                "input": {"ticket": "reset password"},
                "cassette": "cassettes/t1.jsonl",
                "assertions": [{"type": "required_fields", "fields": ["category", "reply"]}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

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

    _write_workflow(repo_dir, workflow_path, suite_dir, baseline_file, action_ref)
    _append_readme(repo_dir, suite_dir, baseline_file)
    _ensure_gitignore(repo_dir)

    if not args.skip_baseline:
        _generate_baseline(repo_dir, suite_dir, baseline_file)

    _check_diff_size(repo_dir, max_diff_lines)

    print("Integration patch prepared at:", repo_dir)
    print("Suite:", suite_path)
    print("Workflow:", workflow_path)
    print("Baseline:", baseline_file)


if __name__ == "__main__":
    main()


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _write_workflow(repo_dir: Path, workflow_path: Path, suite_dir: Path, baseline_file: Path, action_ref: str) -> None:
    template_path = Path(__file__).parent / "templates" / "runledger.yml"
    text = template_path.read_text(encoding="utf-8")
    suite_rel = _relpath(suite_dir, repo_dir)
    baseline_rel = _relpath(baseline_file, repo_dir)
    rendered = (
        text.replace("{{suite_path}}", suite_rel)
        .replace("{{baseline_path}}", baseline_rel)
        .replace("runledger/Runledger@v0.1", action_ref)
    )
    target = repo_dir / workflow_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")


def _append_readme(repo_dir: Path, suite_dir: Path, baseline_file: Path) -> None:
    readme = repo_dir / "README.md"
    note_path = Path(__file__).parent / "templates" / "README_note.md"
    suite_rel = _relpath(suite_dir, repo_dir)
    baseline_rel = _relpath(baseline_file, repo_dir)
    note = note_path.read_text(encoding="utf-8").replace("{{suite_path}}", suite_rel).replace(
        "{{baseline_path}}", baseline_rel
    )
    if readme.exists():
        content = readme.read_text(encoding="utf-8")
        if "RunLedger CI gate" in content:
            return
        readme.write_text(content.rstrip() + "\n\n" + note + "\n", encoding="utf-8")
    else:
        readme.write_text("# Repository\n\n" + note + "\n", encoding="utf-8")


def _ensure_gitignore(repo_dir: Path) -> None:
    gitignore = repo_dir / ".gitignore"
    entry = "runledger_out/"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if entry in content:
            return
        gitignore.write_text(content.rstrip() + "\n" + entry + "\n", encoding="utf-8")
    else:
        gitignore.write_text(entry + "\n", encoding="utf-8")


def _generate_baseline(repo_dir: Path, suite_dir: Path, baseline_file: Path) -> None:
    result = run(["runledger", "run", str(suite_dir), "--mode", "replay"], cwd=repo_dir, check=True)
    match = re.search(r"Artifacts written to:\\s*(.+)", result.stdout)
    if not match:
        raise SystemExit("Unable to locate run output path from RunLedger output.")
    run_dir = match.group(1).strip()
    run(["runledger", "baseline", "promote", "--from", run_dir, "--to", str(baseline_file)], cwd=repo_dir)


def _check_diff_size(repo_dir: Path, max_diff_lines: int) -> None:
    result = run(["git", "diff", "--numstat"], cwd=repo_dir)
    total = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        try:
            added = int(parts[0]) if parts[0].isdigit() else 0
            deleted = int(parts[1]) if parts[1].isdigit() else 0
        except ValueError:
            added = 0
            deleted = 0
        total += added + deleted
    if total > max_diff_lines:
        raise SystemExit(f"Diff too large: {total} lines > max_diff_lines={max_diff_lines}")
