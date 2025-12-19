from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from automation.common import ensure_tool, load_config, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a minimal RunLedger integration patch.")
    parser.add_argument("--config", default="automation/config.yaml", help="Path to config YAML")
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/name form")
    parser.add_argument("--workdir", default=None, help="Workdir base (overrides config)")
    parser.add_argument("--branch", default="runledger/replay-gate", help="Branch name to create")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not modify repo")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    ensure_tool("git")

    workdir = Path(args.workdir or cfg.data.get("output", {}).get("workdir", "automation/workdir"))
    repo_dir = workdir / args.repo.replace("/", "_")

    if args.dry_run:
        print("Dry run: would clone and prepare patch for", args.repo)
        print("Workdir:", repo_dir)
        return

    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    workdir.mkdir(parents=True, exist_ok=True)

    run(["git", "clone", f"https://github.com/{args.repo}.git", str(repo_dir)])
    run(["git", "checkout", "-b", args.branch], cwd=repo_dir)

    print("TODO: generate evals, baseline, and workflow using templates.")
    print("Repo cloned at:", repo_dir)


if __name__ == "__main__":
    main()
