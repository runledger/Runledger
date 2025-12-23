# RunLedger integration notes

This PR adds a small, replay-only RunLedger suite under `{{suite_path}}`.

The included `agent/agent.py` is a minimal JSONL protocol example so the suite can run deterministically with the bundled cassette. To use RunLedger as a real regression gate for this repo, update `agent_command` in `{{suite_path}}/suite.yaml` to run your real agent (or a thin adapter) that speaks the RunLedger protocol.

## Run locally

```bash
runledger run {{suite_path}} --mode replay --baseline {{baseline_path}}
```

## Potential entrypoints in this repo

RunLedger did not execute anything in this repo to generate these hints. It only looked at common config files and folders (README, `pyproject.toml`, `package.json`, `examples/`, etc.).

{{entrypoints_md}}

## Next steps (recommended)

1) Pick the best existing agent/example command in this repo.
2) Add a thin adapter under `{{suite_path}}/agent/` that translates RunLedger protocol messages into calls to that command/library.
3) Update `agent_command` in `{{suite_path}}/suite.yaml` to point at the adapter.

Once wired, you can record real tool cassettes locally, then run replay mode in CI as a deterministic merge gate.

