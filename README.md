# RunLedger

**CI for tool-using agents:** deterministic eval suites + record/replay tool calls + hard assertions + budgets + PR regression gates.

> Treat agents like software: repeatable tests, baselines, diffs, budgets, and merge gates -- not "it worked once."

---

## What this is

This repo provides:

- A **CLI** that runs **deterministic, pass/fail evaluation suites** against an agent under test (any language).
- **Record/replay tool calls** ("cassettes") so CI runs are stable and fast.
- **Hard assertions** (JSONSchema, required fields, regex, tool contracts) and **budgets** (latency, tool calls/errors, tokens/cost when available).
- **Regression gating** vs a baseline: fail CI when success rate drops or budgets spike.
- **Artifacts**: `run.jsonl`, `summary.json`, `junit.xml`, `report.html`.

### What this is not

- Not a generic tracing/observability platform.
- Not "LLM-judge only" scoring as your merge gate.
- Not a hosted monitoring product (though the artifacts are designed to support one later).

---

## Quickstart (5 minutes)

### Install

```bash
pipx install runledger
# or: pip install runledger
```

### Initialize example evals

```bash
runledger init
# creates ./evals and a minimal demo agent + suite
```

### Run locally (record once)

```bash
runledger run ./evals --mode record
```

### Run deterministically (replay)

```bash
runledger run ./evals --mode replay
```

### Open the report

```bash
# report path is printed at end of run
open .agentci/runs/**/report.html
```

---

## How it works

1. You define a **suite** (`suite.yaml`) and **cases** (`cases/*.yaml`).
2. The runner launches your **agent under test** as a subprocess (any language).
3. The agent requests tools via a **stdio JSON protocol**.
4. The runner either:

   * **records** tool results to a cassette (local/dev), or
   * **replays** tool results from a cassette (CI/deterministic).
5. The agent emits a **final JSON output**.
6. The runner applies **assertions** + **budgets**, compares to a **baseline**, writes artifacts, and exits non-zero on regressions.

---

## Agent-under-test protocol (language-agnostic)

**Transport:** newline-delimited JSON messages over stdin/stdout.

**Hard rule:** agent must write **protocol JSON only to stdout**.
Any human logs must go to **stderr** (stdout must stay parseable).

### Runner -> Agent

`task_start`

```json
{ "type": "task_start", "task_id": "t1", "input": { "...": "..." } }
```

`tool_result`

```json
{ "type": "tool_result", "call_id": "c1", "ok": true, "result": { "...": "..." } }
```

### Agent -> Runner

`tool_call`

```json
{ "type": "tool_call", "name": "search_docs", "call_id": "c1", "args": { "q": "..." } }
```

`final_output` (must be JSON)

```json
{ "type": "final_output", "output": { "category": "billing", "reply": "..." } }
```

Optional:

* `log` (structured debug)
* `task_error` (explicit failure)

---

## Eval suite format

### `evals/<suite>/suite.yaml` (example)

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

### `evals/<suite>/cases/t1.yaml` (example)

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

---

## Record/replay tool calls (cassettes)

### Why record/replay?

Agents often depend on external tools (search, DB, HTTP). Live calls in CI are:

* slow
* flaky
* non-deterministic
* expensive

Instead:

* **record once** (live tools) -> write cassette
* **replay in CI** (deterministic) -> stable and fast

### Cassette format (JSONL example)

Each line is one tool invocation:

```json
{"tool":"search_docs","args":{"q":"reset password"},"ok":true,"result":{"hits":[...]}}
{"tool":"create_issue","args":{"title":"Login issue","priority":"p2"},"ok":true,"result":{"id":"ISSUE-123"}}
```

**Replay matching (MVP):**

* exact match on `tool` + canonicalized `args`
* if not found: the case fails with a clear "cassette mismatch" error

---

## Assertions (deterministic)

MVP assertions:

* `json_schema` (validate final output with JSON Schema)
* `required_fields` (keys exist / basic typing)
* `regex` / `contains` (for specific fields)
* `tool_contract`:

  * must call tool X
  * must not call tool Y
  * X before Y (ordering)

Not default-gating (optional later):

* LLM-judge scoring
* semantic similarity scoring

---

## Budgets (merge gates)

MVP budgets:

* `max_wall_ms`
* `max_tool_calls`
* `max_tool_errors`

Optional budgets when agents report metrics:

* `max_tokens_out`
* `max_cost_usd`

---

## Baselines + regression checks

On each run, you can compare against a baseline and fail CI if:

* success rate drops below threshold
* costs spike beyond allowed delta
* latency p95 increases beyond allowed delta

Typical workflow:

* record cassettes locally
* establish a baseline from a known-good run
* run replay mode on every PR and gate merges on regressions

---

## Output artifacts

A run produces:

* `run.jsonl` -- append-only event log (steps, tool calls/results, outputs)
* `summary.json` -- suite + case metrics, pass/fail, regression summary
* `junit.xml` -- CI-native pass/fail (each case maps to a test)
* `report.html` -- static shareable report (no server required)

These files are intentionally stable so they can be:

* diffed in PRs
* uploaded as CI artifacts
* ingested by a future hosted add-on

---

## GitHub Actions (example)

> Replace `<OWNER>/<REPO>` and `<VERSION>` with your action reference.

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
        uses: <OWNER>/<REPO>@<VERSION>
        with:
          path: ./evals
          mode: replay
          baseline: ./baselines/support-triage.json

      - name: Upload eval artifacts
        uses: actions/upload-artifact@v4
        with:
          name: agent-eval-artifacts
          path: .agentci/runs/**
```

---

## Determinism guide (rules of the road)

* Prefer `--mode replay` in CI.
* Ensure agent writes **only JSONL protocol messages** to stdout; logs go to stderr.
* Canonicalize tool call args (stable key ordering, avoid volatile fields).
* Avoid timestamps/randomness in final output; if needed, exclude or normalize before assertions.
* Keep cassettes safe to commit: redact secrets by default.

---

## Roadmap

* `init` templates for Python (OpenAI SDK), LangGraph/LangChain, and Node/TS
* richer budgets (tokens/cost) via optional `task_metrics`
* baseline promotion workflow + PR comments bot
* plugin system for custom assertions
* HTML report trace viewer improvements

---

## Contributing

* Issues and PRs welcome.
* See `CONTRIBUTING.md` for development setup, style, and testing.
* Security issues: see `SECURITY.md`.

---

## License

MIT
