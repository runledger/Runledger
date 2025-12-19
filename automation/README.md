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
python automation/repo_finder.py --config automation/config.yaml --output automation/targets.json
```

4) Review the target list (Gate A). Only then move to integration.

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
