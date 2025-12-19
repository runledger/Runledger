from __future__ import annotations

import argparse
from pathlib import Path

from automation.common import ensure_tool, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a RunLedger integration in a repo.")
    parser.add_argument("--repo-path", required=True, help="Path to cloned repo")
    parser.add_argument("--suite-path", default="evals/runledger", help="Suite directory path")
    parser.add_argument("--baseline", default="baselines/runledger.json", help="Baseline path")
    parser.add_argument("--run-tests", action="store_true", help="Run repo tests if cheap")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_path = Path(args.repo_path).resolve()
    ensure_tool("runledger", ["--help"])

    print("Running RunLedger replay check...")
    run(
        [
            "runledger",
            "run",
            str(repo_path / args.suite_path),
            "--mode",
            "replay",
            "--baseline",
            str(repo_path / args.baseline),
        ],
        cwd=repo_path,
    )

    if args.run_tests:
        print("Running repo tests...")
        run(["python", "-m", "pytest"], cwd=repo_path, check=False)

    print("Verification complete.")


if __name__ == "__main__":
    main()
