# RunLedger

[![CI](https://github.com/runledger/Runledger/actions/workflows/ci.yml/badge.svg)](https://github.com/runledger/Runledger/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/runledger)](https://pypi.org/project/runledger/)
[![PyPI downloads](https://img.shields.io/pypi/dm/runledger)](https://pypi.org/project/runledger/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://pypi.org/project/runledger/)
[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-runledger-181717?logo=github)](https://github.com/marketplace/actions/runledger)
[![License](https://img.shields.io/github/license/runledger/Runledger)](LICENSE)

Website: https://runledger.io

**pytest-style CI for AI agents: replay recorded tool calls and fail the PR on tool-order, schema, or tool-call-count regressions. Recorded tools need no API keys during replay.**

Replay covers requests your agent sends through RunLedger's JSONL tool protocol. Model or network calls made independently by the agent still run live. To keep a test offline, route those calls through the protocol or replace them with fixtures in your adapter. The included demo makes no live model calls.

## New in 0.3.0: action scenarios and production incident replay

Install or upgrade the CLI from PyPI:

```sh
python -m pip install --upgrade runledger
runledger scenario verify --out support-results
runledger incident --help
```

The support-agent pack runs five synthetic refund scenarios with committed effects
tracked separately from tool responses. A timeout after a successful refund exposes
a duplicate-payment bug; the fixed policy passes all five explicit business checks.
Open `support-results/report.html` for the before/after results and action traces.

The incident commands import your supported production JSON export or RunLedger
JSONL log, redact it locally, and replay recorded responses against an explicit
JSONL agent adapter. Calls are matched in order, including repeated identical
requests. An unrecorded path stops as a divergence. Exported HTML, JSON, trace,
and JUnit artifacts distinguish a reproduced failure from passing business rules.
Use `--gate` to fail CI on a reproduced rule violation or inconclusive evidence.

```sh
runledger incident import production-export.json --out sanitized
runledger incident inspect sanitized/incident.json --out inspection
runledger incident promote sanitized/incident.json --to cases/refund-incident.json
```

[Refund demo](https://runledger.io/refund-demo) ·
[Incident replay demo](https://runledger.io/incident-replay) ·
[Production import guide](https://github.com/runledger/Runledger/blob/v0.3.0/docs/production-incidents.md) ·
[Support-agent guide](https://github.com/runledger/Runledger/blob/v0.3.0/docs/support-agent-pack.md)

Review redacted bundles before sharing; custom fields may need additional
redaction paths. Recorded effects are historical evidence from the exporter,
not simulated new provider actions. Replay freezes the JSONL tool boundary;
independent model/network calls remain live. The public example is fictional.

The wheel installs both commands. To run the included adapter examples, use the
`v0.3.0` repository checkout or the optional [full source ZIP](https://runledger.io/templates/support-agent/runledger-scenario-source.zip);
example files are not installed into your current folder by pip. A separate
[portable support pack](https://runledger.io/templates/support-agent/runledger-support-agent.zip)
runs with Python's standard library and no installation.

## Five-minute quickstart

From an empty directory, with Python 3.9+:

```bash
python3 -m pip install "runledger==0.3.0"
runledger init
runledger run ./evals/demo --mode replay --baseline baselines/demo.json
```

`runledger init` writes:

- `evals/demo/` — replay suite, cassette, JSON Schema, and a small Python agent that calls `search_docs`
- `baselines/demo.json` — baseline from that passing run
- `.github/workflows/runledger.yml` — pull-request workflow that runs the same command

A second `runledger init` leaves those files unchanged. `--force` regenerates them. `runledger init --language node` writes a Node agent for the same suite. `init` writes the baseline only when that example agent passes.

The demo exits non-zero unless all three of these hold:

- **Schema.** The final output matches `evals/demo/schema.json` (`category` and `reply`).
- **Tool order.** The agent calls `search_docs` (`call_order` in `evals/demo/cases/t1.yaml`).
- **Tool-call budget.** The run stays within `max_tool_calls: 1`.

A passing run prints `PASS` and writes `runledger_out/demo/<run_id>/` (`summary.json`, `junit.xml`, `report.html`, `run.jsonl`). Commit the init files to run that gate on pull requests.

<table>
  <tr>
    <td width="72%" valign="top">
      <img src="https://raw.githubusercontent.com/runledger/Runledger/v0.3.0/docs/assets/demo.gif" alt="Terminal demo: pip install runledger, runledger init, a replay that prints PASS, then a one-line edit that fails tool order" width="100%">
    </td>
    <td width="28%" valign="top">
      <img src="https://raw.githubusercontent.com/runledger/Runledger/v0.3.0/docs/pr-failing-checks.png" alt="Pull request whose RunLedger check failed" width="100%">
    </td>
  </tr>
</table>

The edit in the demo replaces the `search_docs` tool call with a final output. Replay then prints `FAIL` for `call_order` (`expected: search_docs`, `observed: <none>`). The screenshot is that same kind of check failing on a pull request: https://github.com/ZackMitchell910/runledger-demo/pull/1

The same check as a GitHub Action. `suite.yaml` already points at `baselines/demo.json`, so the action compares against that baseline:

```yaml
- id: evals
  uses: runledger/Runledger@v0.3.0
  with:
    path: ./evals/demo
    mode: replay
    package: runledger==0.3.0
```

`runledger/Runledger@v0.3.0` accepts a `baseline` input and sets `result` (`pass` or `fail`), `exit-code`, and `artifacts-path`. The in-repo self-test calls the action with `uses: ./`.

Page copy for runledger.io lives in `docs/site-quickstart.md`.

## Verify setup and regression coverage

RunLedger 0.3.0 includes `runledger doctor` for static setup checks and an optional replay probe, plus `runledger verify` for repeated passing runs, explicit regression checks, and recovery checks.

The wheel installs the CLI; repository examples require a checkout of the `v0.3.0` tag. To try the self-contained Python example:

```bash
git clone --branch v0.3.0 --depth 1 https://github.com/runledger/Runledger.git runledger-examples
cd runledger-examples
python -m pip install "runledger==0.3.0"
runledger doctor examples/verification --probe
runledger verify examples/verification
```

See [setup and regression verification](https://github.com/runledger/Runledger/blob/v0.3.0/docs/setup-verification.md) for plan format, expected failure matching, runtime limits, and CI evidence. `doctor` without `--probe` does not execute your agent. Execution probes use replay, which does not isolate independent model or network calls.

## RunLedger vs DeepEval and promptfoo

| | RunLedger | DeepEval | promptfoo |
| --- | --- | --- | --- |
| Job | Fail CI when a tool-using agent regresses | Score output quality | Evaluate prompts and model outputs |
| How the run is produced | Runs the agent with recorded results for protocol tool calls | Calls a model to generate or grade output | Calls the provider configured for the eval |
| The check fails when | Tool order, output schema, or the tool-call budget (`max_tool_calls`) | A score misses the threshold you set | An assertion you configured fails |
| API keys in the replay path | Not needed for recorded tools; independent agent calls may need them | Needed when the metric calls a hosted model | Needed when the provider is a hosted API |

DeepEval scores quality. promptfoo evaluates prompts and model outputs. RunLedger is the replay harness that fails the CI check. You can use them together.

## Why this catches the regressions

A change can skip a tool, call tools in a different order, return JSON that no longer matches the schema, or exceed `max_tool_calls`. RunLedger checks the tool trace and returns recorded results for protocol tool calls. Deterministic CI also requires the agent's model calls and other inputs to be fixed or replayed.

The process exits non-zero when tool order, the output schema, or the tool-call budget fails. `max_wall_ms` and `max_tool_errors` are separate gates. Comparing average or p95 wall time to a baseline is opt-in (`max_avg_wall_ms_delta_pct`, `max_p95_wall_ms_delta_pct`).

## Integrations (merged)

- hoangsonww/Agentic-AI-Pipeline - https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24
- zhongyu09/openchatbi - https://github.com/zhongyu09/openchatbi/pull/8
- joshuaalpuerto/mcp-agent - https://github.com/joshuaalpuerto/mcp-agent/pull/3

Try the [real mcp-agent integration](https://github.com/runledger/Runledger/blob/v0.3.0/docs/mcp-agent-guide.md): a pinned upstream agent, fixed model decisions, ten repeat replays, and three deliberate failures. It runs without API keys or live network calls. See the guide for its scope and upstream dependency limitations.

Details: [merged integrations](https://github.com/runledger/Runledger/blob/v0.3.0/docs/integrations.md). For structured feedback after testing, use the [developer trial guide](https://github.com/runledger/Runledger/blob/v0.3.0/docs/developer-trial.md).

## Why a run failed

![RunLedger failure output](https://raw.githubusercontent.com/runledger/Runledger/v0.3.0/docs/pr-failure-log.png)

Artifacts are written to `runledger_out/<suite>/<run_id>/`:

- `report.html`, `summary.json`, `junit.xml`, `run.jsonl`

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
agent_command: ["python3", "agent.py"]
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
* each matching entry is consumed once per case; repeated identical requests receive their recorded results in order
* if no unused matching entry remains: the case fails with a clear "cassette mismatch" error

---

## Assertions (deterministic)

MVP assertions:

* `json_schema` (validate final output with JSON Schema)
* `required_fields` (keys exist)
* `must_call` (must call tool X)
* `must_not_call` (must not call tool Y)
* `call_order` (X before Y; tools do not have to be adjacent)

Not default-gating (optional later):

* LLM-judge scoring
* semantic similarity scoring

---

## Budgets (merge gates)

Budgets that fail a run:

* `max_wall_ms`
* `max_tool_calls`
* `max_tool_errors`

---

## Baselines + regression checks

On each run, you can compare against a baseline and fail CI if:

* success rate drops below threshold
* average or p95 latency increases beyond allowed delta

Typical workflow:

* record cassettes locally
* establish a baseline from a known-good run
* run replay mode on every PR and gate merges on regressions

```bash
runledger baseline promote --from runledger_out/<suite>/<run_id> --to baselines/<suite>.json
runledger run ./evals/<suite> --mode replay --baseline baselines/<suite>.json
```

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
        id: evals
        uses: runledger/Runledger@v0.3.0
        with:
          path: ./evals/demo
          mode: replay
          package: runledger==0.3.0

      - name: Show the action result
        run: echo "result=${{ steps.evals.outputs.result }} exit=${{ steps.evals.outputs.exit-code }}"
```

`runledger init` writes `.github/workflows/runledger.yml`, which installs the CLI and runs the suite with `--baseline`. The action above is the Marketplace entry in `action.yml` at `runledger/Runledger@v0.3.0`. It uploads `runledger_out/**` on success and on failure. The step sets `result`, `exit-code`, and `artifacts-path`, and you can pass `baseline:` to override `suite.yaml`. A failing run fails the job.

---

## Determinism guide (rules of the road)

* Prefer `--mode replay` in CI.
* Ensure agent writes **only JSONL protocol messages** to stdout; logs go to stderr.
* Canonicalize tool call args (stable key ordering, avoid volatile fields).
* Avoid timestamps/randomness in final output; if needed, strip/normalize via `normalization`.
  ```yaml
  normalization:
    strip_keys: ["timestamp", "request_id"]
    strip_paths: ["meta.seed"]
    replace_text:
      - pattern: "\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z"
        replacement: "<timestamp>"
  ```
* Keep cassettes safe to commit: redact secrets by default.

---

## Docs

- `docs/site-quickstart.md` -- five-minute copy for runledger.io
- `docs/quickstart.md` -- install + first run
- `docs/assertions.md` -- assertions, tool contracts, budgets
- `docs/baselines.md` -- baselines, diffing, promotion
- `docs/ci.md` -- CI setup with GitHub Actions
- [Setup and regression verification](https://github.com/runledger/Runledger/blob/v0.3.0/docs/setup-verification.md) -- `doctor` and `verify` commands
- `docs/contracts.md` -- public contracts (YAML, protocol, artifacts)
- `docs/troubleshooting.md` -- common errors and fixes

---

## Roadmap

* `init` templates for Python (OpenAI SDK), LangGraph/LangChain, and Node/TS
* PR comments bot for regression summaries
* plugin system for custom assertions
* HTML report trace viewer improvements

---

## Commercial Support

RunLedger is MIT-licensed and free to self-host. For teams that want done-for-you implementation or ongoing maintenance, we offer:

- Hardening Sprint (fixed-scope implementation to get deterministic CI running fast)
- Assurance (monthly retainer for cassette and case updates, budget tuning, and incident response)

Contact: [runledger.io/community.html#contact](https://runledger.io/community.html#contact)

---

## Contributing

* Issues and PRs welcome.
* See `CONTRIBUTING.md` for development setup, style, and testing.
* Security issues: see `SECURITY.md`.

---

## License

MIT

If this is useful, star [runledger/Runledger](https://github.com/runledger/Runledger).
