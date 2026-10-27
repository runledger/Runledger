# Quickstart

## Install

```bash
pipx install runledger
# or: pip install runledger
```

## Initialize a demo suite

```bash
runledger init
```

This creates:

- `evals/demo/` with a replay suite, cassette, and JSON Schema
- `evals/demo/agent/agent.py` (minimal Python agent that calls `search_docs`)
- `baselines/demo.json`
- `.github/workflows/runledger.yml` (pull-request replay against that baseline)

The case asserts `call_order: [search_docs]`. The suite asserts `schema.json` and `max_tool_calls: 1`. Running `runledger init` again leaves existing files unchanged. `runledger init --force` regenerates them.

To scaffold a Node adapter instead:

```bash
runledger init --language node
```

## Run deterministically (replay)

```bash
runledger run ./evals/demo --mode replay --baseline baselines/demo.json
```

## Record a cassette (local dev)

```bash
runledger run ./evals/demo --mode record
```

## Open the report

```bash
open runledger_out/**/report.html
```
