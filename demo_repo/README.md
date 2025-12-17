# RunLedger Demo Repo (Scaffold)

This folder is a starter for a standalone demo repo that shows CI regression gates in under a minute.

## Quickstart

```bash
pipx install runledger
runledger run ./evals/demo --mode replay --baseline baselines/demo.json
```

## CI

`.github/workflows/ci.yml` runs the suite in replay mode and uploads artifacts.

## Regression branches to create

1. `regression-schema`
   - Edit `evals/demo/schema.json` and add a new required field.
   - Expected failure: JSONSchema assertion.

2. `regression-tools`
   - Edit `evals/demo/agent/agent.py` to call a different tool or skip `search_docs`.
   - Expected failure: tool contract or allowlist failure.

3. `regression-budget`
   - Edit `evals/demo/agent/agent.py` to call `search_docs` twice while budget allows 1.
   - Expected failure: budget gate.

## README assets

- Add a short GIF of a failing PR.
- Include a screenshot or link to a `report.html` artifact.
