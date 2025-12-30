from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from typing import Any


DEFAULT_NOTE = (
    "GitHub Actions note: workflows from first-time contributors/forks may require a maintainer to click "
    "“Approve and run” before checks will execute."
)


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return result.stdout


def _load_json(cmd: list[str]) -> Any:
    return json.loads(_run(cmd))


def _has_note(body: str) -> bool:
    return bool(re.search(r"approve and run", body, flags=re.IGNORECASE))


def _insert_note(body: str, note: str) -> str:
    lines = body.splitlines()
    header_index = None
    for idx, line in enumerate(lines):
        if line.strip() == "## Notes":
            header_index = idx
            break

    if header_index is None:
        return body.rstrip() + "\n\n## Notes\n- " + note + "\n"

    start = header_index + 1
    end = len(lines)
    for idx in range(start, len(lines)):
        if lines[idx].startswith("## ") and lines[idx].strip() != "## Notes":
            end = idx
            break

    insert_at = start
    for idx in range(start, end):
        if lines[idx].lstrip().startswith("- "):
            insert_at = idx + 1

    updated = lines[:insert_at] + [f"- {note}"] + lines[insert_at:]
    return "\n".join(updated).rstrip() + "\n"


def _iter_target_prs(author: str, limit: int) -> list[dict[str, Any]]:
    payload = _load_json(
        [
            "gh",
            "search",
            "prs",
            "--author",
            author,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "repository,number,title,url",
        ]
    )
    targets: list[dict[str, Any]] = []
    for item in payload:
        title = str(item.get("title", ""))
        if re.search(r"runledger|deterministic replay gate", title, flags=re.IGNORECASE):
            targets.append(item)
    return targets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Patch existing RunLedger PR bodies with an Actions approval note.")
    parser.add_argument("--author", default="@me", help="PR author to search for (default: @me)")
    parser.add_argument("--limit", type=int, default=50, help="Max PRs to scan")
    parser.add_argument("--note", default=DEFAULT_NOTE, help="Note line to add under ## Notes")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without editing PRs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prs = _iter_target_prs(author=args.author, limit=args.limit)
    if not prs:
        print("No matching open PRs found.")
        return

    print(f"Found {len(prs)} open PR(s).")
    for pr in prs:
        repo = pr["repository"]["nameWithOwner"]
        number = pr["number"]
        url = pr["url"]
        title = pr["title"]
        body = _load_json(["gh", "pr", "view", str(number), "-R", repo, "--json", "body"])["body"]
        if _has_note(body):
            print(f"SKIP (already has note): {repo}#{number} {url}")
            continue
        updated = _insert_note(body, args.note)
        if args.dry_run:
            print(f"WOULD EDIT: {repo}#{number} {url} ({title})")
            continue

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".md") as handle:
            handle.write(updated)
            path = handle.name
        _run(
            [
                "gh",
                "api",
                "-X",
                "PATCH",
                f"repos/{repo}/issues/{number}",
                "-F",
                f"body=@{path}",
                "--silent",
            ]
        )
        print(f"UPDATED: {repo}#{number} {url}")


if __name__ == "__main__":
    main()
