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

The demo needs no API keys. For your own agent, replay replaces only tool calls sent through RunLedger's JSONL protocol. Model or network calls outside that protocol remain live; route them through the protocol or use fixtures if you need an offline, deterministic test.

Each cassette entry can satisfy one matching tool call per case. Repeated identical calls consume their matching entries in recorded order; an extra call fails with a cassette mismatch.

## Record a cassette (local dev)

```bash
runledger run ./evals/demo --mode record
```

## Open the report

```bash
find runledger_out -name report.html -print
```

In Windows PowerShell, use `Get-ChildItem runledger_out -Filter report.html -Recurse`.
