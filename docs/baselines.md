# Baselines and Diffing

Baselines are stored as JSON summary files and are used to gate regressions.

## Baseline file location

Recommended path:

- `baselines/<suite>.json`

## Promote a baseline

```bash
runledger baseline promote --from runledger_out/<suite>/<run_id> --to baselines/<suite>.json
```

## Diff a run against a baseline

```bash
runledger diff --baseline baselines/<suite>.json --run runledger_out/<suite>/<run_id>
```

## Run with a baseline gate

```bash
runledger run ./evals/<suite> --mode replay --baseline baselines/<suite>.json
```
