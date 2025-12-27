# RunLedger PR-Bot Automation

This folder contains a small, safe-by-default toolkit to help you target repos and generate minimal RunLedger integration PRs.

## Quick start

1) Install GitHub CLI and authenticate:

```bash
gh auth login
```

2) Copy config and fill in your defaults:

```bash
cp automation/config.example.yaml automation/config.yaml
```

3) Find candidate repos:

```bash
python -m automation.repo_finder --config automation/config.yaml --output automation/targets.json
```

4) Review the target list (Gate A). Only then move to integration.

## Integration workflow (recommended)

1) Generate a patch in a workdir clone:

```bash
cp automation/approved_targets.example.txt automation/approved_targets.txt
# add one repo per line: owner/name

python -m automation.repo_integrator --config automation/config.yaml --repo owner/name
```

This writes the integration patch in `automation/workdir/...` and also generates a clean PR body draft in `automation/drafts/` (no PowerShell/backtick issues).
It also writes `evals/runledger/INTEGRATION.md` in the target repo with entrypoint hints (detected by scanning config files like `README`, `pyproject.toml`, `package.json`, and common example folders).

2) Gate B: review the diff in the workdir clone, then commit/push and open the PR (or open an issue first).

## Issue-first outreach (recommended for new repos)

Before opening PRs widely, consider opening a short issue asking if they want a PR. A template is in `automation/templates/issue_body.md`.

You can use `automation/outreach_bot.py` to draft and submit either an issue or a PR:

```bash
python -m automation.outreach_bot --kind issue --repo owner/name --title "Optional RunLedger replay gate?" --body automation/templates/issue_body.md
python -m automation.outreach_bot --kind issue --repo owner/name --title "Optional RunLedger replay gate?" --body automation/templates/issue_body.md --submit --confirm owner/name
```

## GitHub App auth (optional / limited)

If you want PRs to appear as `runledger[bot]`, you need a GitHub App installation token.
Important: GitHub Apps cannot open PRs on external repos unless the target repo owner installs the App.
For third-party repos, PRs should come from a user account (or a separate bot user with a PAT).

Example (token expires ~1 hour):

```bash
token=$(python -m automation.app_token --app-id 12345 --key ~/.config/runledger/app.pem --repo runledger/tuui)
GITHUB_TOKEN="$token" gh pr create --repo AI-QL/tuui --head runledger:runledger/replay-gate --base main \
  --title "Add RunLedger replay gate for agent regressions" \
  --body-file automation/drafts/AI-QL_tuui_pr.md
unset GITHUB_TOKEN
```

Notes:
- RepoFinder still needs your user token because GitHub App tokens cannot use the search API.
- Keep the `.pem` private key out of the repo.

## Guardrails

- Replay-only. No secrets. No live tool calls.
- Keep diffs small (target <200 LOC).
- Default CI mode is `workflow_dispatch` (manual) to avoid surprising existing CI. Switch to `pull_request` once maintainers opt in.
- Two approval gates:
  - Gate A: approve target list.
  - Gate B: approve draft PR before submission.

## Files

- repo_finder.py: GitHub search + scoring.
- repo_integrator.py: Plans or applies a minimal integration patch.
- verifier.py: Runs replay + optional tests and emits a PR summary.
- outreach_bot.py: Drafts issue/PR text, waits for human approval.
- templates/: Workflow + README note templates.
