## What this adds

- A small, replay-only RunLedger suite under `{{suite_path}}` (suite/case/schema/cassette + minimal protocol example agent)
- A short wiring guide at `{{suite_path}}/INTEGRATION.md` (repo-specific entrypoint hints + how to swap in a real agent)
- A baseline file at `{{baseline_path}}`
- A GitHub Actions workflow at `{{workflow_path}}` (optional; you can remove it if you don't want a new CI job)
- `.gitignore` update to ignore `runledger_out/`

## Why

This is a deterministic CI check for agent/tool regressions: tool calls are replayed from a cassette (no live calls), and the run fails on mismatches, assertion failures, or budget regressions.

## How to run locally

```bash
runledger run {{suite_path}} --mode replay --baseline {{baseline_path}}
```

## Notes

- The included `agent/agent.py` is a minimal RunLedger JSONL protocol example. To use this for a real agent, point `agent_command` in `{{suite_path}}/suite.yaml` at your own agent entrypoint (or a thin adapter).
- `{{suite_path}}/INTEGRATION.md` lists a few potential entrypoints found in this repo (by scanning `README`, `pyproject.toml`, `package.json`, and common example folders). No repo code was executed to produce the hints.
- RunLedger repo: https://github.com/runledger/Runledger

