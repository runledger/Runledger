# RunLedger in five minutes

Copy this into an empty directory. You need Python 3.9 or newer.

```bash
python3 -m pip install runledger
runledger init
runledger run ./evals/demo --mode replay --baseline baselines/demo.json
```

`runledger init` writes three things:

- `evals/demo/` — a replay suite, a cassette, `schema.json`, and a small agent that calls `search_docs`
- `baselines/demo.json` — the baseline saved from that passing run
- `.github/workflows/runledger.yml` — a pull-request workflow that runs the same command

Run `runledger init` again and those files stay as they are. Pass `--force` to regenerate them.

The demo command exits 0 only when all three gates hold:

- **Schema.** The agent's final output validates against `evals/demo/schema.json` (`category` and `reply` strings).
- **Tool order.** The agent calls `search_docs`. The case file records that with a `call_order` assertion.
- **Tool-call budget.** The run stays within `max_tool_calls: 1` in `evals/demo/suite.yaml`.

A passing run prints `PASS` and writes `runledger_out/demo/<run_id>/` with `summary.json`, `junit.xml`, `report.html`, and `run.jsonl`.

Commit the init files. On the next pull request, `.github/workflows/runledger.yml` installs RunLedger and replays the suite against `baselines/demo.json`.

To call the action instead of the workflow file:

```yaml
- id: evals
  uses: runledger/Runledger@v0.2.2
  with:
    path: ./evals/demo
    mode: replay
```

The suite file's `baseline_path` is `baselines/demo.json`, so this compares against the baseline from `runledger init`.

[`action.yml`](https://github.com/runledger/Runledger/blob/main/action.yml) at `runledger/Runledger@v0.2.2` sets three outputs:

- `result` — `pass` when the process exits 0, otherwise `fail`
- `exit-code` — the process exit code
- `artifacts-path` — the artifact directory (`runledger_out` for the default upload path)

The same release accepts a `baseline` input. A failing run fails the job. This repository's self-test workflow calls the action with `uses: ./`.

More detail: [quickstart](https://github.com/runledger/Runledger/blob/main/docs/quickstart.md), [assertions](https://github.com/runledger/Runledger/blob/main/docs/assertions.md), and [CI](https://github.com/runledger/Runledger/blob/main/docs/ci.md).
