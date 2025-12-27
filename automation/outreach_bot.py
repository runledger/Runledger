from __future__ import annotations

import argparse
from pathlib import Path

from automation.common import ensure_tool, run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Draft RunLedger outreach issue/PR text.")
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/name form")
    parser.add_argument(
        "--kind",
        choices=["pr", "issue"],
        default="pr",
        help="What to create when --submit is set",
    )
    parser.add_argument(
        "--title",
        default="Add optional replay-only agent regression check",
        help="PR/issue title",
    )
    parser.add_argument("--body", required=True, help="Path to markdown body")
    parser.add_argument("--submit", action="store_true", help="Create PR/issue via gh (requires approval)")
    parser.add_argument(
        "--confirm",
        default=None,
        help="Type the repo name (owner/name) to confirm submission (Gate B)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    body_path = Path(args.body)
    if not body_path.exists():
        raise SystemExit(f"Body file not found: {body_path}")

    body = body_path.read_text(encoding="utf-8")
    print("Draft PR title:")
    print(args.title)
    print("\nDraft PR body:")
    print(body)

    if not args.submit:
        print("\nSubmit flag not set. Review before submitting.")
        return

    if args.confirm != args.repo:
        raise SystemExit(
            "\n".join(
                [
                    "Refusing to submit without explicit confirmation (Gate B).",
                    f"Re-run with: --confirm {args.repo}",
                ]
            )
        )

    ensure_tool("gh")
    if args.kind == "issue":
        run(["gh", "issue", "create", "--repo", args.repo, "--title", args.title, "--body", body])
        print("Issue created.")
        return

    run(["gh", "pr", "create", "--repo", args.repo, "--title", args.title, "--body", body])
    print("PR created.")


if __name__ == "__main__":
    main()
