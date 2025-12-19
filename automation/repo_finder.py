from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import json

import sys

from automation.common import Config, ensure_tool, load_config, run, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find target repos for RunLedger integration.")
    parser.add_argument("--config", default="automation/config.yaml", help="Path to config YAML")
    parser.add_argument("--output", default=None, help="Output JSON path (overrides config)")
    parser.add_argument("--check-ci", action="store_true", help="Check for .github/workflows presence")
    return parser.parse_args()


def _score_repo(repo: dict, cfg: dict, has_ci: bool) -> float:
    stars = float(repo.get("stargazers_count", 0))
    updated = repo.get("pushed_at") or repo.get("updated_at")
    days = 3650.0
    if updated:
        dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
    recency = max(0.0, 365.0 - min(days, 365.0)) / 365.0

    scoring = cfg.get("scoring", {})
    stars_weight = float(scoring.get("stars_weight", 0.4))
    recency_weight = float(scoring.get("recency_weight", 0.4))
    ci_weight = float(scoring.get("ci_weight", 0.2))

    star_score = min(stars / 1000.0, 1.0)
    ci_score = 1.0 if has_ci else 0.0
    return star_score * stars_weight + recency * recency_weight + ci_score * ci_weight


def _has_ci(full_name: str) -> bool:
    result = run(
        ["gh", "api", "-X", "GET", f"repos/{full_name}/contents/.github/workflows"],
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.stderr:
        print(
            f"Warning: unable to check CI for {full_name}: {result.stderr.strip()}",
            file=sys.stderr,
        )
    return False


def _search(query: str, max_results: int) -> list[dict]:
    items: list[dict] = []
    per_page = min(100, max_results)
    for page in range(1, 11):
        result = run(
            [
                "gh",
                "api",
                "-X",
                "GET",
                "search/repositories",
                "-f",
                f"q={query}",
                "-f",
                f"per_page={per_page}",
                "-f",
                f"page={page}",
            ]
        )
        payload = json.loads(result.stdout)
        batch = payload.get("items", [])
        if not batch:
            break
        items.extend(batch)
        if len(items) >= max_results:
            break
    return items[:max_results]


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    ensure_tool("gh")

    search_cfg = cfg.data.get("search", {})
    queries = search_cfg.get("queries", [])
    min_stars = int(search_cfg.get("min_stars", 0))
    max_age_days = int(search_cfg.get("max_age_days", 3650))
    require_ci = bool(search_cfg.get("require_ci", False))
    max_results = int(search_cfg.get("max_results", 50))

    found: dict[str, dict] = {}
    for q in queries:
        for repo in _search(q, max_results=max_results):
            if repo.get("archived") or repo.get("fork"):
                continue
            if repo.get("stargazers_count", 0) < min_stars:
                continue
            updated = repo.get("pushed_at") or repo.get("updated_at")
            if updated:
                dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                age_days = (datetime.now(timezone.utc) - dt).days
                if age_days > max_age_days:
                    continue
            full_name = repo.get("full_name")
            if not full_name:
                continue
            found[full_name] = repo

    results = []
    for full_name, repo in found.items():
        ci_present = _has_ci(full_name) if (require_ci or args.check_ci) else False
        if require_ci and not ci_present:
            continue
        score = _score_repo(repo, cfg.data, ci_present)
        results.append(
            {
                "full_name": full_name,
                "html_url": repo.get("html_url"),
                "stars": repo.get("stargazers_count", 0),
                "language": repo.get("language"),
                "pushed_at": repo.get("pushed_at") or repo.get("updated_at"),
                "has_ci": ci_present,
                "score": round(score, 4),
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    results = results[:max_results]

    output_path = Path(args.output or cfg.data.get("output", {}).get("targets_json", "automation/targets.json"))
    write_json(output_path, {"generated_at": datetime.now(timezone.utc).isoformat(), "targets": results})

    print(f"Wrote {len(results)} targets to {output_path}")


if __name__ == "__main__":
    main()
