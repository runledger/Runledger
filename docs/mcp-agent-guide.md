# Gate a real mcp-agent tool loop with RunLedger

This example exercises the published `@joshuacalpuerto/mcp-agent` **Agent implementation**, rather than a standalone script that imitates an agent. It runs `generateStructuredResult()`, discovers registered tools with `listTools()`, dispatches them through the upstream `callTool()` method, feeds tool results into subsequent model turns, and parses the final JSON response.

The test asks a support agent how to reset a password. Its contract is concrete: search documentation, read the returned page, produce `category`, `reply`, and `source`, and make no more than two tool calls.

## Replay boundary

The real orchestration code runs. Model decisions are **authored fixtures**, and the two tool responses are **authored cassettes**. Neither is presented as captured production traffic. This checks orchestration and integration contracts; it does not measure model quality or test a live MCP server.

```text
RunLedger task_start
  -> actual Agent.generateStructuredResult()
     -> fixed model decision: search_docs
     -> actual Agent.callTool()
        -> registered function emits tool_call JSONL
        <- RunLedger returns cassette tool_result
     -> fixed model decision: read_doc
     -> actual Agent.callTool() -> same bridge
     -> fixed final model response
  <- upstream Agent parses JSON -> final_output
RunLedger checks schema, tool order, and call count
```

The adapter never replaces `Agent.generate`, `listTools`, or `callTool`. Only the registered function `execute` callbacks cross the JSONL boundary. The fixed model checks that each previous tool result reached the next turn, so a disconnected tool path fails instead of producing a false passing demo. Upstream lifecycle events are included in `run.jsonl` as additional evidence.

Independent model calls normally remain live in RunLedger replay. Here, `FixtureLLM` replaces those calls explicitly. The adapter denies Node fetch/socket/TLS connection attempts, and the acceptance checker forwards no API credentials. Those guard assertions are useful for this small local test; they are not a general sandbox.

## Install and run

Use Python 3.9+ and Node.js 22+. Start from a checkout of this repository containing `examples/mcp-agent`, and run commands from its root:

```bash
python -m pip install "runledger==0.2.4"
npm --prefix examples/mcp-agent ci --ignore-scripts
python examples/mcp-agent/verify.py --repeats 10
```

The first two commands install dependencies and need network access. The acceptance runs use local fixtures. `mcp-agent@1.1.1` and its transitive dependencies are frozen for this optional compatibility example; several have known security advisories. Read the [upstream attribution and advisory details](../examples/mcp-agent/UPSTREAM.md). This pin is not a recommendation for a production dependency, and installing the RunLedger CLI does not install it.

Expected final output:

```text
PASS: 10/10 unchanged replays; 3/3 deliberate regressions caught
Evidence: .../acceptance.json
```

The checker writes a fresh directory below `examples/mcp-agent/runledger_out/`. `acceptance.json` records versions, all exit codes, exact gates, tool sequences, upstream lifecycle events, outbound-network denial probes, and a behavior hash. Ten equal hashes mean the tool arguments and final output matched across the passing runs; timestamps and wall-clock timings are intentionally excluded.

Each run retains `console.txt`, `summary.json`, `run.jsonl`, `junit.xml`, and `report.html`. The checker exits 1 if any passing replay fails, any deliberate regression passes or fails for the wrong reason, or a network-denial probe is missing. It does not count a missing dependency or startup crash as a successful regression test. The evidence describes local automated checks, not three human developers completing an onboarding trial.

To run only the successful case:

```bash
runledger run examples/mcp-agent/evals/pass --mode replay
```

## Watch each gate fail

All four suites use the same schema, cassette, and adapter. Only the final scenario argument changes. `fixture-llm.mjs` makes one deliberate change for each scenario.

| Scenario | Deliberate change | Expected gate |
| --- | --- | --- |
| `missing-field` | Delete `reply` from the final model fixture | `json_schema` reports the missing required field |
| `wrong-order` | Reverse the two model tool decisions | `call_order` reports `search_docs -> read_doc` was not satisfied |
| `extra-tool` | Request `search_docs` again after both tools | `max_tool_calls` reports limit 2, actual 3; the third result is never dispatched |

Run these individually; each command should exit **1**:

```bash
runledger run examples/mcp-agent/evals/missing-field --mode replay
runledger run examples/mcp-agent/evals/wrong-order --mode replay
runledger run examples/mcp-agent/evals/extra-tool --mode replay
```

The successful suite's core policy is:

```yaml
assertions:
  - type: json_schema
    schema_path: ../../schema.json
  - type: call_order
    order: [search_docs, read_doc]
budgets:
  max_wall_ms: 20000
  max_tool_calls: 2
  max_tool_errors: 0
```

These contracts gate directly, so this example does not need an aggregate baseline to detect its three regressions. When adding latency or pass-rate comparison to a larger suite, promote a known-good run with `runledger baseline promote`, then configure the desired regression thresholds.

## Add the check to CI

This workflow verifies all 13 runs using the released CLI. RunLedger itself remains a Python CLI; Node is required by this particular upstream agent.

```yaml
name: mcp-agent replay
on: [pull_request]
jobs:
  contracts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python -m pip install "runledger==0.2.4"
      - run: npm --prefix examples/mcp-agent ci --ignore-scripts
      - run: python examples/mcp-agent/verify.py --repeats 10 --output-dir runledger_out/mcp-acceptance
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: mcp-agent-acceptance
          path: runledger_out/mcp-acceptance
```

For a single passing-suite gate, after installing the example's Node dependencies, the Marketplace action can replace the CLI run:

```yaml
- uses: runledger/Runledger@v0.2.4
  with:
    path: examples/mcp-agent/evals/pass
    mode: replay
    package: runledger==0.2.4
```

## Adapt the pattern to your agent

Keep your real application entrypoint and framework loop. Register a bridge at the actual external-operation boundary. In this framework, the `functions` API lets us do that without patching private methods. Map RunLedger results back to the MCP `content` envelope the agent expects.

Choose and document your model boundary. A fixed model fixture tests deterministic orchestration. Capturing model responses through an additional protocol tool can test a larger replay path. A live model tests different behavior and can need credentials, cost money, and vary between runs.

Start with one real user scenario, review its fixtures for sensitive data, then add assertions that describe a failure you care about. Deliberately break that scenario once before making the check required. Passing a canned example proves the installation and integration mechanism; it does not prove your own application is covered.

The upstream project and the original maintainer discussion are linked in [UPSTREAM.md](../examples/mcp-agent/UPSTREAM.md). The npm source revision and package integrity are pinned there and in the lockfile.
