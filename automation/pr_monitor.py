from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from automation.common import ensure_tool, run


@dataclass(frozen=True)
class PullRequest:
    repo: str
    number: int
    title: str
    url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor open RunLedger integration PRs.")
    parser.add_argument(
        "--author",
        default=None,
        help="GitHub username to filter by (defaults to current gh user)",
    )
    parser.add_argument(
        "--head",
        default="runledger/replay-gate",
        help="Head branch name to filter by",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max PRs to fetch")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write a Markdown summary",
    )
    return parser.parse_args()


def _gh_json(args: list[str]) -> object:
    result = run(["gh", *args], check=False)
    if result.returncode != 0:
        combined = "\n".join([result.stdout.strip(), result.stderr.strip()]).strip()
        raise SystemExit(f"gh command failed: gh {' '.join(args)}\n{combined}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse gh JSON output for: gh {' '.join(args)}") from exc


def _get_current_user() -> str:
    result = run(["gh", "api", "user", "--jq", ".login"], check=False)
    if result.returncode != 0:
        combined = "\n".join([result.stdout.strip(), result.stderr.strip()]).strip()
        raise SystemExit(f"Unable to determine current gh user:\n{combined}")
    return result.stdout.strip().strip('"')


def _load_open_prs(*, author: str, head: str, limit: int) -> list[PullRequest]:
    payload = _gh_json(
        [
            "search",
            "prs",
            "--author",
            author,
            "--head",
            head,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "repository,number,title,url",
        ]
    )
    prs: list[PullRequest] = []
    if not isinstance(payload, list):
        return prs
    for item in payload:
        if not isinstance(item, dict):
            continue
        repo = item.get("repository", {}).get("nameWithOwner") if isinstance(item.get("repository"), dict) else None
        number = item.get("number")
        title = item.get("title")
        url = item.get("url")
        if (
            not isinstance(repo, str)
            or not isinstance(number, int)
            or not isinstance(title, str)
            or not isinstance(url, str)
        ):
            continue
        prs.append(PullRequest(repo=repo, number=number, title=title, url=url))
    return prs


def _summarize_checks(status_check_rollup: object) -> tuple[str, list[str]]:
    if not isinstance(status_check_rollup, list) or len(status_check_rollup) == 0:
        return ("NONE", ["No checks reported (workflow may be manual or needs approval)."])

    failures = 0
    pending = 0
    successes = 0
    cancelled = 0
    notes: list[str] = []

    for item in status_check_rollup:
        if not isinstance(item, dict):
            continue
        typename = item.get("__typename")
        if typename == "CheckRun":
            conclusion = item.get("conclusion")
            status = item.get("status")
            name = item.get("name")

            if isinstance(name, str) and "cla" in name.lower():
                if conclusion is None or (
                    isinstance(conclusion, str) and conclusion.upper() in {"NEUTRAL", "SKIPPED"}
                ):
                    notes.append("CLA may be required.")

            if isinstance(status, str) and status.upper() not in {"COMPLETED"}:
                pending += 1
                continue

            if isinstance(conclusion, str):
                c = conclusion.upper()
                if c == "SUCCESS":
                    successes += 1
                elif c == "CANCELLED":
                    cancelled += 1
                elif c in {"FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}:
                    failures += 1
                else:
                    pending += 1
            else:
                pending += 1

        elif typename == "StatusContext":
            context = item.get("context")
            state = item.get("state")
            if isinstance(context, str) and isinstance(state, str):
                s = state.upper()
                if "cla" in context.lower() and s in {"PENDING", "FAILURE"}:
                    notes.append("CLA pending.")
                if context.lower() == "vercel" and s == "FAILURE":
                    notes.append("Vercel check failing (fork deploy auth).")
                if s == "SUCCESS":
                    successes += 1
                elif s == "FAILURE":
                    failures += 1
                else:
                    pending += 1

    if failures > 0:
        overall = "FAIL"
    elif pending > 0:
        overall = "PENDING"
    elif cancelled > 0 and successes == 0:
        overall = "CANCELLED"
    else:
        overall = "PASS"

    summary = f"{overall} (ok={successes}, pending={pending}, fail={failures}, cancelled={cancelled})"
    deduped_notes = []
    seen = set()
    for note in notes:
        if note in seen:
            continue
        seen.add(note)
        deduped_notes.append(note)
    return (summary, deduped_notes)


def _render_markdown(prs: list[PullRequest]) -> str:
    lines = []
    lines.append("| Repo | PR | Checks | Notes |")
    lines.append("| --- | --- | --- | --- |")
    for pr in prs:
        view = _gh_json(["pr", "view", pr.url, "--json", "statusCheckRollup"])
        rollup = view.get("statusCheckRollup") if isinstance(view, dict) else None
        checks, notes = _summarize_checks(rollup)
        notes_text = " ".join(notes) if notes else ""
        pr_link = f"[#{pr.number}]({pr.url})"
        lines.append(f"| `{pr.repo}` | {pr_link} | {checks} | {notes_text} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    ensure_tool("gh")

    author = args.author or _get_current_user()
    prs = _load_open_prs(author=author, head=args.head, limit=args.limit)
    md = _render_markdown(prs)

    if args.output:
        from pathlib import Path

        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
        print(f"Wrote: {path}")
    else:
        print(md, end="")


if __name__ == "__main__":
    main()

