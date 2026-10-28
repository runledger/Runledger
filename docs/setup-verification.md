# Check setup and prove a regression gate

`runledger doctor` and `runledger verify` are **unreleased, source-only commands**. The published `runledger==0.2.4` package does not include them. Install a checkout containing these changes, using the Python environment that will run your agent:

```bash
python -m pip install -e .
runledger doctor examples/verification
runledger doctor examples/verification --probe
runledger verify examples/verification
```

Activate that environment first. Bare Python aliases in `agent_command` resolve from the agent's PATH; invoking the CLI with an absolute Python path alone does not select the agent's interpreter. An explicit interpreter path in `agent_command` can also select the intended environment.

Run these commands from the RunLedger repository root. The [self-contained example](../examples/verification/suite.yaml) needs Python 3.9+ and the RunLedger dependencies; it needs no Node installation, API keys, or live model. Its fixture agent deliberately supports three broken behaviors. This demonstrates installation and contract verification, not coverage of your own application.

With the defaults, verification runs this one-case suite three times unchanged, checks three deliberate regressions, and runs the original case after each regression: nine case executions. It exits 0 only if all checks pass.

## Inspect setup without executing the agent

```bash
runledger doctor examples/verification --json
```

The default check reads suite/case YAML, checks unique case IDs, locates the executable and obvious interpreter script paths, validates assertion shapes and JSON Schema files, checks budget values, reads cassettes, verifies cassette tools against the registry, and validates a configured baseline. Empty cassettes are valid for cases that make no tool calls.

It does not launch the agent, import user tool modules, write artifacts, or fetch external schema references. It reports dependency readiness as a warning because file inspection cannot establish that arbitrary agent imports or protocol handling will work. Unsupported token and cost limits also produce warnings because the runner does not enforce them. Warnings alone do not fail the check; a failed check makes the exit status 1.

The JSON report contains `schema_version`, `ok`, `suite_path`, and a `checks` list. Each check has `name`, `status` (`pass`, `warning`, or `fail`), and `message`, with location or count fields where relevant.

## Execute one setup probe

```bash
runledger doctor examples/verification --probe --case password-reset --timeout 15
```

`--probe` first runs the static checks. If they pass, it launches the agent and replays one case. Without `--case`, it selects the first case in sorted case-file order. `--case` requires `--probe`.

The probe tests startup, protocol handling, cassette matching, and the selected case's assertions and budgets. It does not compare that one case against a whole-suite baseline. A configured baseline must still be readable and structurally valid during the static checks. Probe artifacts are written beneath `runledger_out/doctor/<run_id>/probe/`; use `--output-dir` to change the root.

Both execution commands force RunLedger's tool mode to replay. **Replay is not a network sandbox:** the agent still runs ordinary code with its inherited environment. Model calls, network requests, and side effects outside the JSONL tool boundary remain live unless your adapter explicitly replaces or isolates them. A passing probe establishes only that the selected path worked.

## Declare deliberate regressions

`verify` reads `verification.yaml` beside `suite.yaml` by default. Use `--plan path/to/verification.yaml` to choose another plan. The [example plan](../examples/verification/verification.yaml) includes this check:

```yaml
schema_version: 1
regressions:
  - name: skipped-lookup
    case_id: password-reset
    input: {scenario: skip-tool}
    expect:
      assertion: must_call
      details: {missing: [search_docs]}
      tool_calls: 0
```

Here the fixture agent emits valid final JSON but skips `search_docs`. The existing `must_call` assertion must catch that omission. Your own adapter must implement any mutation mode you put in a plan; RunLedger does not infer or inject a source-code mutation.

Each regression requires a unique `name`, an existing `case_id`, an `expect` object, and at least one of:

- `input`: replaces the selected case's entire input object; it does not merge keys. Include every input the mutated path needs.
- `agent_command`: replaces the entire argument array for that probe. Use it to launch a wrapper or a supported failure mode in your adapter. It is an executable argument list, not a shell command string.

The plan requires integer `schema_version: 1` and at least one regression. Names are 1–64 ASCII letters, digits, underscores, or hyphens and must start with a letter or digit. Unknown plan, regression, and expectation fields are rejected.

Both replacements can be used together. They affect in-memory execution copies. RunLedger does not patch the checked-in agent, cases, cassettes, assertions, budgets, or baseline.

Existing paths in a plan's `agent_command` resolve relative to the plan's directory. Existing command paths in `suite.yaml` resolve relative to the suite directory. Executable symlinks retain their virtual environment location. Arguments that do not identify existing paths are preserved; remaining relative paths use the process's current working directory. The module name after `-m`, and inline code and following arguments after `-c`, `-e`, `-p`, `--eval`, or `--print`, remain literal. Use existing script paths or absolute paths, and run from your project's documented working directory.

For example, the [mcp-agent plan](../examples/mcp-agent/verification.yaml) lives beside `agent.mjs` and selects a broken adapter mode with:

```yaml
agent_command: [node, agent.mjs, wrong-order]
```

After installing that optional example's Node dependencies as described in its [guide](mcp-agent-guide.md), run the generic verifier from this source checkout:

```bash
runledger verify examples/mcp-agent/evals/pass --plan examples/mcp-agent/verification.yaml --repeats 10
```

This does not replace the example's separate `verify.py` checker for the released 0.2.4 CLI. The upstream dependency and fixture limitations in the mcp-agent guide still apply.

## Require the intended failure

`expect` must specify exactly one failure category:

| Field | Supported values |
| --- | --- |
| `assertion` | `json_schema`, `required_fields`, `must_call`, `must_not_call`, `call_order` |
| `budget` | `max_wall_ms`, `max_tool_calls`, `max_tool_errors` |

That assertion type or budget must already be configured on the selected case through the suite or case configuration. Optional criteria make the expected failure more specific:

| Field | Matching rule |
| --- | --- |
| `details` | Expected dictionary keys must match recursively. Lists must have the same length, order, and matching elements. For assertions these are the assertion's structured details; for budgets they are the budget failure fields, such as `limit` and `actual`. |
| `message_contains` | A nonempty, case-sensitive substring of the failure message. |
| `tool_calls` | The exact nonnegative integer count of observed tool-call requests. |

The probe must produce **exactly one** assertion or budget failure, of the expected type, and satisfy every supplied criterion. An assertion failure also requires an actual final output. A missing dependency, agent startup error, cassette mismatch, unrelated failure, or multiple failures does not count as a successful detection. A broken case that passes makes verification fail.

An extra-call check in the example expects:

```yaml
expect:
  budget: max_tool_calls
  details: {limit: 1, actual: 2}
  tool_calls: 2
```

This tests the existing one-call limit; the plan cannot loosen that limit to make the check pass.

## Repeatability, recovery, and time limits

```bash
runledger verify examples/verification --repeats 10 --timeout 15 --json
```

`--repeats` is the number of unchanged full-suite runs, defaults to 3, and accepts 1–100. Every unchanged run must pass. If a baseline is configured, those original full-suite runs also apply its regression gates. A failing unchanged run stops verification before deliberate regressions are attempted.

For each case, the verifier compares a SHA-256 fingerprint of ordered tool-call payloads, tool-result payloads, and final output against the first passing run. Protocol envelope timestamps, call IDs, and log events are excluded. Payload fields with those names remain part of the comparison. Normalization configured for tool results and final output applies before fingerprinting; tool arguments remain part of the trace. Passing assertions with different behavior still fail the repeatability check.

After each completed negative probe, the verifier runs the original selected case again and requires a passing result with the original fingerprint. This recovery check also runs when a negative probe returns the wrong failure. Recovery failure stops further probes. Negative probes and single-case recoveries do **not** compare against a whole-suite baseline; that would compare different case populations.

`--timeout` defaults to 30 seconds and must be finite and positive. It caps each case's wall time, including agent startup, while preserving any tighter suite/case budget. It is not a limit for the entire verification command. A planned `max_wall_ms` failure requires a timeout at least as large as that case's configured wall-time limit, so the verification cap cannot substitute for the budget being tested.

## Read the evidence and gate CI

Verification writes `runledger_out/verification/<run_id>/` by default:

- `verification.json`: aggregate outcome, expected/actual checks, fingerprints as `behavior_sha256` lists of `{case_id, sha256}` records, and paths to individual runs.
- `verification.junit.xml`: the **verification gate** for a CI test-report collector.
- `unchanged-*`, `regression-*`, and `recovery-*` directories: each run's `summary.json`, `run.jsonl`, `report.html`, and `probe.junit.xml`.

Raw `probe.junit.xml` files intentionally retain failures from broken agents, including regressions the verifier correctly detected. Collect **only `**/verification.junit.xml`** as the verification test result. Upload the whole directory as diagnostic artifacts, but do not treat all raw probe XML files as independent CI failures. The `verify` process itself exits 0 when verification passes and 1 when it fails. The regular `runledger run` command continues to write its normal `junit.xml`.

The setup probe also writes raw `probe.junit.xml`; its CLI exit status is its gate. Validation errors found before execution starts are reported on the console or through `--json` and may have no artifact directory.

For your own agent, start with one important user scenario and one specific regression. Keep the real application entrypoint, declare which external behavior is fixed or replayed, and confirm that the expected failure is useful before making the gate required. Repeatability proves consistency of the tested path; it does not establish live model quality or coverage of untested paths.
