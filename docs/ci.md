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
      - uses: <OWNER>/<REPO>@<VERSION>
        with:
          path: ./evals/demo
          mode: replay
```
