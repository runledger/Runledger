from __future__ import annotations

import argparse
import os
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
    workflow_mode = str(integration_cfg.get("workflow_mode", "pull_request")).strip()
    replay_only = bool(integration_cfg.get("replay_only", True))
    max_diff_lines = int(integration_cfg.get("max_diff_lines", 200))
    drafts_dir = Path(cfg.data.get("output", {}).get("drafts_dir", "automation/drafts"))

    if args.dry_run:
        print("Dry run: would clone and prepare patch for", args.repo)
        print("Workdir:", repo_dir)
        print("Suite dir:", evals_dir)
        print("Baseline dir:", baseline_dir)
        print("Workflow:", workflow_path)
        print("Action ref:", action_ref)
        print("Workflow mode:", workflow_mode)
        print("Drafts dir:", drafts_dir)
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
                "def main():",
                "    for line in sys.stdin:",
                "        line = line.strip()",
                "        if not line:",
                "            continue",
                "        msg = json.loads(line)",
                "        if msg.get(\"type\") == \"task_start\":",
                "            ticket = msg.get(\"input\", {}).get(\"ticket\", \"\")",
                "            send({\"type\": \"tool_call\", \"name\": \"search_docs\", \"call_id\": \"c1\", \"args\": {\"q\": ticket}})",
                "        elif msg.get(\"type\") == \"tool_result\":",
                "            send({\"type\": \"final_output\", \"output\": {\"category\": \"account\", \"reply\": \"Reset password instructions sent.\"}})",
                "            break",
                "",
                "if __name__ == \"__main__\":",
                "    main()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    if not args.skip_baseline:
        _generate_baseline(repo_dir, suite_dir, baseline_file)
        _normalize_baseline_paths(baseline_file, repo_dir)
        suite_yaml["baseline_path"] = _relpath(baseline_file, suite_dir)
        suite_path.write_text(yaml.safe_dump(suite_yaml, sort_keys=False), encoding="utf-8")

    _write_workflow(repo_dir, workflow_path, suite_dir, baseline_file, action_ref, workflow_mode)
    _append_readme(repo_dir, suite_dir, baseline_file)
    _ensure_gitignore(repo_dir)
    _write_pr_draft(drafts_dir, args.repo, repo_dir, suite_dir, baseline_file, workflow_path)

    _check_diff_size(repo_dir, max_diff_lines)

    print("Integration patch prepared at:", repo_dir)
    print("Suite:", suite_path)
    print("Workflow:", workflow_path)
    print("Baseline:", baseline_file)


def _relpath(path: Path, base: Path) -> str:
    try:
        rel = os.path.relpath(path.resolve(), start=base.resolve())
        return Path(rel).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_workflow(
    repo_dir: Path,
    workflow_path: Path,
    suite_dir: Path,
    baseline_file: Path,
    action_ref: str,
    workflow_mode: str,
) -> None:
    if workflow_mode == "none":
        return

    template_name = {
        "pull_request": "runledger_pull_request.yml",
        "workflow_dispatch": "runledger_workflow_dispatch.yml",
    }.get(workflow_mode)
    if template_name is None:
        raise SystemExit(f"Unsupported workflow_mode: {workflow_mode}")

    template_path = Path(__file__).parent / "templates" / template_name
    text = template_path.read_text(encoding="utf-8")
    suite_rel = _relpath(suite_dir, repo_dir)
    baseline_rel = _relpath(baseline_file, repo_dir)
    rendered = (
        text.replace("{{suite_path}}", suite_rel)
        .replace("{{baseline_path}}", baseline_rel)
        .replace("{{action_ref}}", action_ref)
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
        if "<!-- runledger:note:start -->" in content or "## RunLedger CI gate" in content:
            return
        readme.write_text(content.rstrip() + "\n\n" + note + "\n", encoding="utf-8")
    else:
        readme.write_text("# Repository\n\n" + note + "\n", encoding="utf-8")


def _write_pr_draft(
    drafts_dir: Path,
    repo_slug: str,
    repo_dir: Path,
    suite_dir: Path,
    baseline_file: Path,
    workflow_path: Path,
) -> None:
    template_path = Path(__file__).parent / "templates" / "PR_body.md"
    if not template_path.exists():
        return

    suite_rel = _relpath(suite_dir, repo_dir)
    baseline_rel = _relpath(baseline_file, repo_dir)
    workflow_rel = workflow_path.as_posix()

    body = (
        template_path.read_text(encoding="utf-8")
        .replace("{{suite_path}}", suite_rel)
        .replace("{{baseline_path}}", baseline_rel)
        .replace("{{workflow_path}}", workflow_rel)
    )

    drafts_dir.mkdir(parents=True, exist_ok=True)
    draft_path = drafts_dir / f"{repo_slug.replace('/', '_')}_pr.md"
    draft_path.write_text(body, encoding="utf-8")
    print("Draft PR body written to:", draft_path)


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
    suite_path = suite_dir.resolve()
    result = run(["runledger", "run", str(suite_path), "--mode", "replay"], cwd=repo_dir, check=False)
    output = "\n".join([result.stdout, result.stderr]).strip()
    if result.returncode != 0:
        raise SystemExit(f"runledger run failed:\n{output}")
    clean_output = re.sub(r"\x1b\[[0-9;]*m", "", output)
    run_dir = ""
    for line in clean_output.splitlines():
        if "Artifacts written to:" in line:
            run_dir = line.split("Artifacts written to:", 1)[1].strip()
            break
    if not run_dir:
        raise SystemExit(f"Unable to locate run output path from RunLedger output:\n{output}")
    run(
        [
            "runledger",
            "baseline",
            "promote",
            "--from",
            run_dir,
            "--to",
            str(baseline_file.resolve()),
        ],
        cwd=repo_dir,
    )


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


def _normalize_baseline_paths(baseline_file: Path, repo_dir: Path) -> None:
    data = json.loads(baseline_file.read_text(encoding="utf-8"))
    repo_dir = repo_dir.resolve()

    suite = data.get("suite")
    if isinstance(suite, dict):
        suite_path = suite.get("suite_path")
        suite["suite_path"] = _normalize_path_value(suite_path, repo_dir)
        agent_command = suite.get("agent_command")
        if isinstance(agent_command, list):
            suite["agent_command"] = [
                _normalize_path_value(item, repo_dir) if isinstance(item, str) else item
                for item in agent_command
            ]

    cases = data.get("cases")
    if isinstance(cases, list):
        for case in cases:
            if not isinstance(case, dict):
                continue
            replay = case.get("replay")
            if not isinstance(replay, dict):
                continue
            cassette_path = replay.get("cassette_path")
            replay["cassette_path"] = _normalize_path_value(cassette_path, repo_dir)

    baseline_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_path_value(value: str | None, base_dir: Path) -> str | None:
    if value is None or not isinstance(value, str):
        return value
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        rel = path.resolve().relative_to(base_dir)
    except ValueError:
        return path.as_posix()
    return rel.as_posix()


if __name__ == "__main__":
    main()
