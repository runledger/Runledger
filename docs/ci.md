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
        if: always()
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
      - id: evals
        uses: runledger/Runledger@v0.2.3
        with:
          path: ./evals/demo
          mode: replay
      - name: Read action outputs
        run: |
          echo "result=${{ steps.evals.outputs.result }}"
          echo "exit-code=${{ steps.evals.outputs.exit-code }}"
          echo "artifacts-path=${{ steps.evals.outputs.artifacts-path }}"
```

`result` is `pass` when the process exits 0 and `fail` otherwise. `exit-code` is that process status. `artifacts-path` is the upload path with a trailing `/**` removed (`runledger_out` by default). The action uploads `runledger_out/**` on success and on failure.

`runledger init` writes `.github/workflows/runledger.yml` for the CLI path above. This repo's `.github/workflows/action-self-test.yml` runs the action with `uses: ./`.

If `suite.yaml` includes `baseline_path` and you omit `baseline`, RunLedger compares against that file. `runledger/Runledger@v0.2.3` also accepts `baseline` when you want to override the suite file. That tag sets `result`, `exit-code`, and `artifacts-path`, and a failing run fails the job.
