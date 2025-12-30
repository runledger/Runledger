## What this adds

- A small, replay-only RunLedger suite under `evals/runledger` (suite/case/schema/cassette + minimal protocol example agent)
- A short wiring guide at `evals/runledger/INTEGRATION.md` (repo-specific entrypoint hints + how to swap in a real agent)
- A baseline file at `baselines/runledger-demo.json`
- A GitHub Actions workflow at `.github/workflows/runledger.yml` (optional; you can remove it if you don't want a new CI job)
- `.gitignore` update to ignore `runledger_out/`

## Why

This is a deterministic CI check for agent/tool regressions: tool calls are replayed from a cassette (no live calls), and the run fails on mismatches, assertion failures, or budget regressions.

## How to run locally

```bash
runledger run evals/runledger --mode replay --baseline baselines/runledger-demo.json
```

## Notes

- The included `agent/agent.py` is a minimal RunLedger JSONL protocol example. To use this for a real agent, point `agent_command` in `evals/runledger/suite.yaml` at your own agent entrypoint (or a thin adapter).
- `evals/runledger/INTEGRATION.md` lists a few potential entrypoints found in this repo (by scanning `README`, `pyproject.toml`, `package.json`, and common example folders). No repo code was executed to produce the hints.
- GitHub may not run new workflows from fork PRs by default. If you don't see any checks, a maintainer may need to approve Actions for this PR, or you can run the workflow manually from the Actions tab (if it's configured as `workflow_dispatch`).
- RunLedger repo: https://github.com/runledger/Runledger
