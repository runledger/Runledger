<!-- runledger:note:start -->
## RunLedger replay check (optional)

This repo includes a small RunLedger suite under `{{suite_path}}` for deterministic, replay-only checks of tool-using agents.

Run locally:

```bash
runledger run {{suite_path}} --mode replay --baseline {{baseline_path}}
```

This replays recorded tool calls from a cassette (no live calls) and fails on mismatches, assertion failures, or budget regressions.

To wire this to a real agent, update `agent_command` in `{{suite_path}}/suite.yaml` to point at your agent entrypoint (or a thin adapter) that speaks the RunLedger JSONL protocol.

See `{{suite_path}}/INTEGRATION.md` for repo-specific wiring hints (detected from config files and example folders).
<!-- runledger:note:end -->
