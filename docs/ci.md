# CI Setup (GitHub Actions)

## Using the CLI directly

```yaml
name: runledger-evals
on:
  pull_request:

jobs:
  evals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install RunLedger
        run: |
          python -m pip install --upgrade pip
          python -m pip install runledger
      - name: Run deterministic evals
        run: runledger run ./evals/demo --mode replay --baseline baselines/demo.json
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: runledger-artifacts
          path: runledger_out/**
```

## Using the composite action

```yaml
name: runledger-evals
on:
  pull_request:

jobs:
  evals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: runledger/Runledger@v0.1
        with:
          path: ./evals/demo
          mode: replay
```

Note: if your `suite.yaml` includes `baseline_path`, RunLedger will automatically compute a regression diff vs that baseline (no extra flags needed).
