Hi! I maintain RunLedger (https://github.com/runledger/Runledger), a small CLI for deterministic CI checks for tool-using agents (record once, replay in CI).

Would you be open to a small, optional PR that adds:

- `evals/runledger/` (suite + one case + schema + cassette)
- `baselines/runledger-demo.json`
- an optional GitHub Actions workflow to run the replay check (manual or on PR, depending on what you prefer)

The goal is to catch agent/tool regressions in CI without live tool calls (record once, replay in CI; fail on mismatch).

If you're interested, what is the best existing agent/example entrypoint in this repo to wire the suite to?

