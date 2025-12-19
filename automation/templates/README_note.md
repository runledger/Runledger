## RunLedger CI gate

This repo includes a deterministic CI gate for tool-using agents:

```bash
runledger run {{suite_path}} --mode replay --baseline {{baseline_path}}
```

It replays recorded tool calls and fails the PR on schema/tool/budget regressions.
