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

Configure optional gates under `regression` in `suite.yaml`:

```yaml
regression:
  min_pass_rate: 1.0
  max_avg_wall_ms_delta_pct: 0.2
  max_p95_wall_ms_delta_pct: 0.2
```

The wall-time deltas are fractions (`0.2` permits a 20% increase). Legacy names `min_success_rate` and `max_p95_wall_ms_increase_pct` are accepted aliases. Unknown names are rejected instead of silently skipping the intended gate.
