## Summary
- add a replay-only RunLedger eval suite (suite/case/schema/cassette + stub agent)
- add a baseline file for regression gating
- add a GitHub Actions workflow using `runledger/Runledger@v0.1`
- add a small README note + ignore `runledger_out/`

## How to run locally
```bash
runledger run evals/runledger --mode replay --baseline baselines/runledger-demo.json
```

## Notes
- no external calls; replay-only cassette
- feel free to remove the suite/workflow if it is not desired
