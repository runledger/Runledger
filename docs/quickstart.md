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

- `evals/demo/` with a working suite and cassette
- `evals/demo/agent/agent.py` (minimal Python agent)
- `baselines/demo.json`

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
