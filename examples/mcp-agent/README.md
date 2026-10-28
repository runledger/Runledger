# mcp-agent orchestration replay

This optional example imports the published `@joshuacalpuerto/mcp-agent@1.1.1` implementation. Its actual `Agent.generateStructuredResult()` loop dispatches two registered tools through RunLedger. Model decisions and tool results are local fixtures; no live model, MCP server, or API key is needed.

The RunLedger wheel does not contain example files. Use a checkout of the `v0.2.5` tag, with Python 3.9+ and Node.js 22+. If you do not already have that checkout:

```bash
git clone --branch v0.2.5 --depth 1 https://github.com/runledger/Runledger.git runledger-examples
cd runledger-examples
python -m pip install "runledger==0.2.5"
npm --prefix examples/mcp-agent ci --ignore-scripts
python examples/mcp-agent/verify.py --repeats 10
```

The checker succeeds only when 10 identical replays pass, three deliberate regressions fail at their intended gates, upstream lifecycle events are present, and the adapter's outbound network denial probes pass. It prints the location of `acceptance.json` and per-run artifacts. These are automated checks, not results from developer trials.

RunLedger 0.2.5 also accepts this example's generic verification plan:

```bash
runledger doctor examples/mcp-agent/evals/pass --probe
runledger verify examples/mcp-agent/evals/pass --plan examples/mcp-agent/verification.yaml --repeats 10
```

That command verifies ten unchanged runs, three deliberate regressions, and recovery after each regression. Use `verification.junit.xml` for its CI gate. The separate `verify.py` adds the upstream lifecycle and network-denial checks.

Read the [integration guide](../../docs/mcp-agent-guide.md) for individual commands, the adapter boundary, and CI setup. Read [UPSTREAM.md](UPSTREAM.md) before using this pinned upstream dependency: it has known advisories and is included only as a local compatibility example, not a production dependency recommendation. It is not a dependency of the RunLedger CLI.
