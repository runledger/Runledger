# RunLedger Demo Repo (Scaffold) [![CI](https://github.com/runledger/runledger-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/runledger/runledger-demo/actions/workflows/ci.yml)

This folder is a starter for a standalone demo repo that shows CI regression gates in under a minute.

## Quickstart

```bash
pipx install runledger
runledger run ./evals/demo --mode replay --baseline baselines/demo.json
```

## CI

`.github/workflows/ci.yml` runs the suite in replay mode and uploads artifacts.
Expected outcomes:
- `main`: green
- `regression-schema`: red (JSONSchema failure, missing `next_steps`)
- `regression-tools`: red (tool contract/allowlist failure)
- `regression-budget`: red (budget gate `max_tool_calls: 0`)

## Screenshots / report

![PR blocked](https://raw.githubusercontent.com/runledger/Runledger/main/docs/pr-failing-checks.png)
![Failure reason](https://raw.githubusercontent.com/runledger/Runledger/main/docs/pr-failure-log.png)

Sample report snapshot: see the failure log above or open any CI run artifact to view `report.html`.

## Regression branches to create

1. `regression-schema`
   - Edit `evals/demo/schema.json` and add a new required field.
   - Expected failure: JSONSchema assertion.

2. `regression-tools`
   - Edit `evals/demo/agent/agent.py` to call a different tool or skip `search_docs`.
   - Expected failure: tool contract or allowlist failure.

3. `regression-budget`
   - Edit `evals/demo/suite.yaml` to set `max_tool_calls: 0`.
   - Expected failure: budget gate.

## Regression templates

`regressions/` contains ready-to-copy files for each regression branch. Each folder only includes the files that differ from `main`.

```bash
git checkout -b regression-schema
cp -r regressions/regression-schema/* .
git add -A
git commit -m "Regression: schema required field"
```

## README assets

- (Optional) Add a short GIF of a failing PR and a screenshot or link to a `report.html` artifact.
