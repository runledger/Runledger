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

## GitHub App auth (optional)

If you want PRs to appear as `runledger[bot]`, use a GitHub App installation token
when running `gh pr create`.

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
- Two approval gates:
  - Gate A: approve target list.
  - Gate B: approve draft PR before submission.

## Files

- repo_finder.py: GitHub search + scoring.
- repo_integrator.py: Plans or applies a minimal integration patch.
- verifier.py: Runs replay + optional tests and emits a PR summary.
- outreach_bot.py: Drafts issue/PR text, waits for human approval.
- templates/: Workflow + README note templates.
