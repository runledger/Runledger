# RunLedger Summary

## Overview

RunLedger is a CI harness for tool-using agents. It makes agent evaluation deterministic by recording tool calls once, replaying them in CI, and enforcing hard contracts, budgets, and baselines. The goal is to catch regressions before merge and keep agent workflows stable as prompts, tools, models, and external dependencies change.

RunLedger is not an eval metrics framework. Use metrics tooling (for example, DeepEval-style scoring) for quality scoring and benchmarking, and use RunLedger for deterministic CI gates and regression control.

## What RunLedger Does

- Deterministic replay: record tool calls and results once, replay them in CI.
- Hard contracts: enforce JSON schema, required fields, tool allowlists, and tool ordering.
- Budgets: cap wall time, tool calls, and tool errors (plus optional tokens/costs when reported).
- Baselines: compare runs to a known-good baseline and fail on regressions.
- CI-ready outputs: write JSONL logs, summary JSON, JUnit, and HTML reports.

## How It Works (End-to-End)

1. You define a suite (`suite.yaml`) and its cases (`cases/*.yaml`).
2. RunLedger launches your agent under test as a subprocess (any language).
3. The agent and runner exchange newline-delimited JSON over stdin/stdout.
4. RunLedger either:
   - records tool results to a cassette (record mode), or
   - replays tool results from a cassette (replay mode).
5. The agent emits a final JSON output.
6. RunLedger applies assertions and budgets, compares against a baseline, writes artifacts, and exits non-zero on regressions.

## Core Concepts

### Suite
A suite bundles cases, tool registry, contracts, budgets, and baseline paths into a single CI unit.

### Case
Each case defines a task input and a cassette for deterministic replay. Cases can add or override assertions and budgets to target specific tasks.

### Cassette
A cassette is a JSONL log of tool calls and results recorded during a live run. RunLedger replays these entries in CI to remove external nondeterminism. Matching is exact on tool name and canonicalized arguments; missing matches fail the case with a cassette mismatch error.

### Assertions
Assertions are hard gates applied to the agent's final output and tool behavior:

- `json_schema` for JSON Schema validation.
- `required_fields` to enforce required keys and basic typing.
- `regex` and `contains` for field-level checks.
- `tool_contract` for tool allowlist/denylist and ordering requirements.

### Budgets
Budgets enforce hard caps that fail the run when exceeded:

- `max_wall_ms`
- `max_tool_calls`
- `max_tool_errors`
- Optional: `max_tokens_out`, `max_cost_usd` when agents report metrics.

### Baselines
Baselines store a known-good run summary and enable regression gating. On each run, RunLedger compares against the baseline and fails CI if success rate drops, costs spike beyond allowed deltas, or latency p95 increases.

### Artifacts
RunLedger outputs stable artifacts suitable for PR diffs and CI uploads:

- `run.jsonl`: append-only event log of steps, tool calls/results, and outputs.
- `summary.json`: suite and case metrics, pass/fail, and regression summary.
- `junit.xml`: CI-native pass/fail results.
- `report.html`: static, shareable report with no server required.

## User Interaction

### CLI Workflow
Quickstart flow:

```bash
pipx install runledger
runledger init
runledger run ./evals --mode record
runledger baseline promote --from <RUN_DIR> --to baselines/<suite>.json
runledger run ./evals --mode replay
```

Artifacts are written to `runledger_out/<suite>/<run_id>/`.

### Suite Configuration (Example)

`evals/<suite>/suite.yaml`:

```yaml
suite_name: support-triage
agent_command: ["python", "agent.py"]
mode: replay            # replay | record | live
cases_path: cases
tool_registry:
  - search_docs
  - create_issue

assertions:
  - type: json_schema
    schema_path: schema.json

budgets:
  max_wall_ms: 20000
  max_tool_calls: 10
  max_tool_errors: 0

baseline_path: baselines/support-triage.json
```

`evals/<suite>/cases/t1.yaml`:

```yaml
id: t1
description: "triage a login ticket"
input:
  ticket: "User cannot login"
  context:
    plan: "pro"
cassette: cassettes/t1.jsonl

assertions:
  - type: required_fields
    fields: ["category", "reply"]

budgets:
  max_wall_ms: 5000
```

### Agent-Under-Test Protocol
Transport is newline-delimited JSON over stdin/stdout.

Hard rule: the agent must write protocol JSON only to stdout. Any human logs must go to stderr so stdout stays parseable.

Runner -> Agent:

`task_start`

```json
{ "type": "task_start", "task_id": "t1", "input": { "...": "..." } }
```

`tool_result`

```json
{ "type": "tool_result", "call_id": "c1", "ok": true, "result": { "...": "..." } }
```

Agent -> Runner:

`tool_call`

```json
{ "type": "tool_call", "name": "search_docs", "call_id": "c1", "args": { "q": "..." } }
```

`final_output`

```json
{ "type": "final_output", "output": { "category": "billing", "reply": "..." } }
```

Optional messages:

- `log` for structured debug.
- `task_error` for explicit failures.

### Modes
Suite mode can be one of:

- `record` to write cassettes from live tool calls.
- `replay` to use cassettes for deterministic runs in CI.
- `live` for direct tool execution without replay.

## Record/Replay Details

### Cassette Format
Each line is one tool invocation:

```json
{"tool":"search_docs","args":{"q":"reset password"},"ok":true,"result":{"hits":[...]}}
{"tool":"create_issue","args":{"title":"Login issue","priority":"p2"},"ok":true,"result":{"id":"ISSUE-123"}}
```

### Replay Matching (MVP)
- Exact match on `tool` plus canonicalized `args`.
- If no match is found, the case fails with a cassette mismatch error.

## Baselines and Regression Checks
Typical workflow:

```bash
runledger baseline promote --from runledger_out/<suite>/<run_id> --to baselines/<suite>.json
runledger run ./evals/<suite> --mode replay --baseline baselines/<suite>.json
```

Runs can fail if:
- Success rate drops below threshold.
- Costs spike beyond allowed deltas.
- Latency p95 increases beyond allowed deltas.

## CI Integration
Example GitHub Actions workflow:

```yaml
name: agent-evals
on:
  pull_request:

jobs:
  evals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run deterministic evals (replay)
        uses: ZackMitchell910/runledger@v0.1.0
        with:
          path: ./evals/demo
          mode: replay

      - name: Upload eval artifacts
        uses: actions/upload-artifact@v4
        with:
          name: agent-eval-artifacts
          path: runledger_out/**
```

## Determinism Guidance

- Prefer `--mode replay` in CI.
- Keep stdout strictly JSON protocol messages; send logs to stderr.
- Canonicalize tool call args (stable key ordering, avoid volatile fields).
- Avoid timestamps or randomness in final outputs; normalize or exclude if needed.
- Keep cassettes safe to commit by redacting secrets.

## Hosted and Commercial Support

RunLedger is MIT-licensed and free to self-host. Hosted add-on features are planned for teams that want managed storage, shared baselines, and run history.

For done-for-you implementation or ongoing maintenance, RunLedger offers:

- Hardening Sprint (fixed-scope implementation to get deterministic CI running fast)
- Assurance (monthly retainer for case and cassette updates, budget tuning, and incident response)

Contact: https://runleder.io/community.html#contact

## License

MIT
