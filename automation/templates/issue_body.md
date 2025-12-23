Hi! I maintain RunLedger (https://github.com/runledger/Runledger), a small CLI that runs deterministic, replay-only eval suites for tool-using agents.

Would you be open to a small, optional PR that adds:

- `evals/runledger/` (suite + one case + schema + cassette)
- `baselines/runledger-demo.json`
- an optional GitHub Actions workflow to run the replay check

The goal is to make agent/tool regressions visible in CI without live tool calls (record once, replay in CI).

If you're interested, what is the best existing agent/example entrypoint in this repo to wire the suite to?

