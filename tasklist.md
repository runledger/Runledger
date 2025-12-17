## Task list for Codex (descriptive, implementation-ready)

Below is a prioritized backlog Codex can execute as a sequence of PRs. Each task includes: goal, concrete files/modules, key behaviors, and acceptance criteria. Start with **Phase 1** to get a working replay-only vertical slice end-to-end.


## Status

- Completed: Tasks 1-13 (Phase 1)

## Notes

- Schema paths are resolved relative to the suite directory.
- Cassette paths are resolved relative to the suite directory.
- Demo suite lives under examples/evals/demo and runs via `runledger run examples/evals/demo`.
- Artifacts are written under `.agentci/runs/<suite>/<timestamp>`.

---

# Phase 1 — Replay-only vertical slice (end-to-end MVP)

## Task 1 [DONE] — Repository scaffolding + packaging

**Goal:** A pip-installable Python CLI with a stable module layout and dev tooling.

**Codex should:**

* Create a `pyproject.toml` using `setuptools` (or `hatchling`) with an entrypoint CLI.
* Add core dependencies:

  * `typer`, `rich`
  * `pydantic` (v2)
  * `pyyaml`
  * `jsonschema`
  * `jinja2` (even if report comes later)
* Add dev dependencies:

  * `pytest`, `pytest-timeout`
  * `ruff`, `mypy` (optional but recommended)
* Use `src/` layout.

**Files to create:**

* `pyproject.toml`
* `src/<pkg_name>/__init__.py`
* `src/<pkg_name>/cli.py`
* `src/<pkg_name>/__main__.py` (calls `cli.app()`)
* `README.md` (stub: install + “hello” run)
* `.gitignore` (include run artifacts)
* `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`

**Acceptance criteria:**

* `pip install -e .` works
* `<cli_name> --help` works
* Running `<cli_name>` prints Typer help (no exceptions)

---

## Task 2 [DONE] — Define internal data models for suite + cases (Pydantic)

**Goal:** Strong config validation early; YAML errors become actionable.

**Codex should implement Pydantic models:**

* `SuiteConfig`:

  * `suite_name: str`
  * `agent_command: list[str]` (subprocess command array)
  * `mode: Literal["replay","record","live"]` (Phase 1 supports replay only; validate but error if not replay)
  * `cases_path: str`
  * `tool_registry: list[str]` (allowed tools)
  * `assertions: list[AssertionSpec]` (default assertions)
  * `budgets: BudgetSpec` (parse but not enforce yet in Phase 1)
  * `baseline_path: str | None`
  * `output_dir: str | None` (default to something deterministic like `.agentci/runs`)
* `CaseConfig`:

  * `id: str`
  * `description: str | None`
  * `input: dict` (JSON object)
  * `cassette: str`
  * `assertions: list[AssertionSpec] | None`
  * `budgets: BudgetSpec | None`

**Define `AssertionSpec` minimal:**

* `type: str`
* `...` (type-specific fields via `extra="allow"` initially, then tighten later)

**Define `BudgetSpec` minimal (parsed only in Phase 1):**

* `max_wall_ms: int | None`
* `max_tool_calls: int | None`
* `max_tool_errors: int | None`
* `max_tokens_out: int | None`
* `max_cost_usd: float | None`

**Files to create:**

* `src/<pkg_name>/config/models.py`

**Acceptance criteria:**

* Loading an invalid YAML (missing required fields) produces a clear, typed error message
* `SuiteConfig.model_validate(...)` and `CaseConfig.model_validate(...)` pass for valid examples

---

## Task 3 [DONE] — YAML loader (suite + cases)

**Goal:** Load a suite + all case files deterministically.

**Codex should:**

* Implement `load_suite(path: Path) -> SuiteConfig`
* Implement `load_cases(suite_dir: Path, cases_path: str) -> list[CaseConfig]`

  * Deterministic ordering: sort case filenames, then read.
* Resolve relative paths:

  * `cases_path` relative to suite directory
  * each `cassette` path relative to suite directory (or case file directory; choose one rule and document it)

**Files to create:**

* `src/<pkg_name>/config/loader.py`

**Acceptance criteria:**

* Given `examples/evals/demo/suite.yaml` and `cases/*.yaml`, it loads suite+cases without ambiguity
* Cases are always loaded in the same order on repeated runs

---

## Task 4 [DONE] — Protocol message models + strict JSONL I/O (stdout-only)

**Goal:** Runner and agent communicate reliably with newline-delimited JSON on stdout; logs go to stderr.

**Codex should define message schemas:**

* Runner → Agent:

  * `task_start`: `{type, task_id, input}`
  * `tool_result`: `{type, call_id, ok, result, error?}`
* Agent → Runner:

  * `tool_call`: `{type, name, call_id, args}`
  * `final_output`: `{type, output}` where `output` is JSON object
  * (optional) `log`: `{type, level, message, data?}` (still goes through protocol, but should not be required)

**Strict I/O rule:**

* Runner reads **agent stdout as JSONL**.
* If a line is not valid JSON, runner fails the case with an error:

  * Include the invalid line snippet
  * Instruct: “print logs to stderr, not stdout”

**Files to create:**

* `src/<pkg_name>/protocol/messages.py`
* `src/<pkg_name>/protocol/jsonl.py` (reader/writer utilities)

**Acceptance criteria:**

* JSONL reader:

  * reads line-by-line
  * yields typed message objects or a structured parse error
* Writer writes one JSON object per line with `\n`

---

## Task 5 [DONE] — Subprocess management (spawn agent, send/receive messages)

**Goal:** Robustly run an agent command and exchange protocol messages with timeouts.

**Codex should:**

* Implement `AgentProcess` wrapper:

  * start subprocess with pipes
  * provide `send(message)` and `recv()` (blocks until next JSONL line or timeout)
  * capture stderr output (buffer last N lines for debugging in failures)
  * ensure process cleanup (terminate on failure / context manager)

**Timeouts (Phase 1):**

* Per-case wall clock timeout default 30s (configurable later via budgets)
* If timeout occurs, fail case with reason: “case timeout waiting for agent message”

**Files to create:**

* `src/<pkg_name>/runner/subprocess.py`

**Acceptance criteria:**

* Agent can be started and stopped cleanly
* If agent exits early, runner reports a clear error and includes stderr tail

---

## Task 6 [DONE] — Canonical JSON utility (for tool-call matching)

**Goal:** Deterministic matching for cassette replay.

**Codex should implement:**

* `canonicalize_json(obj) -> obj`:

  * dict keys sorted recursively
  * preserve list order
  * normalize floats/ints carefully (do not coerce types; just ensure stable serialization)
* `canonical_dumps(obj) -> str`:

  * `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
  * works with nested objects

**Files to create:**

* `src/<pkg_name>/util/canonical_json.py`

**Acceptance criteria:**

* Same logical args object yields identical canonical string across runs

---

## Task 7 [DONE] — Cassette format + replay lookup

**Goal:** Replay tool calls deterministically from a recorded cassette.

**Cassette format (Phase 1): JSONL**
Each line is an entry:

```json
{
  "tool": "search_docs",
  "args": {...},
  "ok": true,
  "result": {...}
}
```

**Codex should implement:**

* `load_cassette(path) -> list[CassetteEntry]`
* `find_match(entries, tool_name, args) -> CassetteEntry | None`

  * match on `tool_name` and `canonical_dumps(args)`
* If mismatch:

  * fail case with an error that includes:

    * tool name requested
    * canonical args
    * list of available entries’ tool names + a short args preview

**Files to create:**

* `src/<pkg_name>/cassette/models.py`
* `src/<pkg_name>/cassette/loader.py`
* `src/<pkg_name>/cassette/match.py`

**Acceptance criteria:**

* When agent requests a tool_call that is not present, runner fails with a precise mismatch message
* Matching is exact and deterministic

---

## Task 8 [DONE] — Runner engine (single case, replay mode)

**Goal:** Execute one case end-to-end: task_start → tool loop → final_output → assertions → artifacts.

**Codex should implement:**

* `run_case(suite, case) -> CaseResult`
* Message loop:

  1. send `task_start` with `task_id=case.id` and `input=case.input`
  2. read messages until `final_output`
  3. on `tool_call`, validate tool is allowed (`suite.tool_registry`)
  4. lookup cassette entry and reply with `tool_result`
  5. record events to an in-memory trace list (for later artifact writing)

**Phase 1 restriction:**

* If suite.mode != replay, exit with a clear message (“Only replay mode supported in MVP”)

**Files to create:**

* `src/<pkg_name>/runner/engine.py`
* `src/<pkg_name>/runner/models.py` (CaseResult, SuiteResult, Failure objects)

**Acceptance criteria:**

* With a working example agent + cassette, the case passes and returns structured results
* With invalid tool call, case fails with “tool not allowed” error
* With cassette mismatch, case fails deterministically

---

## Task 9 [DONE] — Assertion engine (MVP assertions)

**Goal:** Deterministic pass/fail without LLM judges.

**Implement assertion types:**

1. `required_fields`

   * config: `fields: list[str]`
   * fail if output missing key
2. `json_schema`

   * config: `schema_path: str`
   * validate output against JSON Schema using `jsonschema`

**Assertion engine design:**

* `apply_assertions(output, trace, suite, case) -> list[AssertionFailure]`
* Merge assertions:

  * suite assertions as defaults
  * case assertions override/extend (choose rule; simplest: concatenate suite assertions then case assertions)

**Files to create:**

* `src/<pkg_name>/assertions/base.py`
* `src/<pkg_name>/assertions/required_fields.py`
* `src/<pkg_name>/assertions/json_schema.py`
* `src/<pkg_name>/assertions/engine.py`

**Acceptance criteria:**

* A failing schema produces a readable failure message (path, expected vs actual if available)
* A missing required field produces a clear failure message

---

## Task 10 [DONE] — Artifacts: run.jsonl, summary.json, junit.xml

**Goal:** Produce standard outputs and fail CI via exit code.

**Artifacts (Phase 1):**

* `run.jsonl`: event log (append-only)

  * include events: `task_start`, `tool_call`, `tool_result`, `final_output`, `case_end`
  * include timestamps and case_id
* `summary.json`: suite-level + case-level result summary
* `junit.xml`: one `<testcase>` per case, failures as `<failure message="...">`

**Codex should:**

* Create a run directory (deterministic structure):

  * `.agentci/runs/<suite_name>/<YYYYMMDD-HHMMSS>` or `<run_id>`
* Write artifacts there
* Return that run directory path to CLI for printing

**Files to create:**

* `src/<pkg_name>/artifacts/run_log.py`
* `src/<pkg_name>/artifacts/summary.py`
* `src/<pkg_name>/artifacts/junit.py`

**Acceptance criteria:**

* After a run, artifacts exist in output dir
* `junit.xml` is valid XML and shows failures in CI systems
* Exit code is non-zero if any case failed

---

## Task 11 [DONE] — CLI `run` command (wires everything together)

**Goal:** Users can run `cli run ./evals/demo` and get artifacts + correct exit code.

**CLI behavior:**

* `cli run <suite_dir>`

  * loads suite.yaml
  * loads cases
  * executes suite
  * prints: pass/fail summary + output dir path
  * returns exit code 0/1

**Flags (Phase 1 minimal):**

* `--output-dir` (optional override)
* `--mode` (optional; must be replay in Phase 1)
* `--case <id>` (run a single case by id)

**Files to modify:**

* `src/<pkg_name>/cli.py`

**Acceptance criteria:**

* Running the example suite yields a passing run and prints the report directory
* `--case t1` runs only that case

---

## Task 12 [DONE] — Example agent (Python) + example eval suite + cassette

**Goal:** A demo that proves the runner works without any external APIs.

**Codex should create:**

* `examples/demo_agent_py/agent.py`:

  * reads JSONL from stdin
  * on task_start:

    * emits tool_call `search_docs` with args derived from input
    * waits tool_result
    * emits final_output JSON with required fields
  * prints debug logs to stderr only
* `examples/evals/demo/suite.yaml`
* `examples/evals/demo/cases/t1.yaml`
* `examples/evals/demo/schema.json`
* `examples/evals/demo/cassettes/t1.jsonl`

**Acceptance criteria:**

* `cli run examples/evals/demo` passes deterministically on any machine
* If you edit `schema.json` to require a new field, the run fails with schema error

---

## Task 13 [DONE] — Integration test for the full vertical slice

**Goal:** Prevent regressions in the runner itself.

**Codex should write:**

* A pytest integration test that:

  * runs `cli run examples/evals/demo --case t1`
  * asserts exit code 0
  * asserts artifacts exist and contain expected keys
* Another test that introduces a known regression (e.g., modify schema or use a failing fixture) and asserts exit code 1.

**Files to create:**

* `tests/integration/test_replay_demo.py`

**Acceptance criteria:**

* `pytest` passes locally
* Tests run in CI quickly (<30s)

---

# Phase 2 — Multi-case, budgets, tool contracts (core usability)

## Task 14 [DONE]— Multi-case suite execution + aggregation

**Goal:** Run all cases in suite with stable ordering and aggregated metrics.

**Codex should:**

* Implement `run_suite(...) -> SuiteResult`
* Compute:

  * total cases
  * passed/failed
  * success_rate
  * total tool calls/errors
  * wall time per case + suite totals

**Acceptance criteria:**

* Suite with multiple cases produces correct aggregation and stable ordering

---

## Task 15 [DONE]— Budget enforcement (case + suite)

**Goal:** Fail cases when budgets exceeded.

**Enforce (MVP):**

* `max_wall_ms`
* `max_tool_calls`
* `max_tool_errors`

**Behavior:**

* Budget failures become case failures with a dedicated failure type.

**Acceptance criteria:**

* Add a case budget that is intentionally too low and verify deterministic failure

---

## Task 16 [DONE]— Tool contract assertions (must/must-not/order)

**Goal:** Deterministic behavioral checks beyond output shape.

**Implement assertion types:**

* `must_call`: tool name(s)
* `must_not_call`: tool name(s)
* `call_order`: list like `["search_docs", "create_issue"]` must occur in that order (not necessarily adjacent)

**Acceptance criteria:**

* A demo regression agent that skips a tool call fails with “must_call” failure

---

# Phase 3 — Baselines + regression gating (merge gate value)

## Task 17 — Define baseline data model and write/read baseline files

**Goal:** A stable baseline format for diffs and CI gating.

**Baseline fields (minimum):**

* suite metadata: suite_name, schema_version
* per-case: pass/fail, wall_ms, tool_calls, tool_errors
* suite aggregates: success_rate, avg_wall_ms, p95_wall_ms

**Acceptance criteria:**

* Baseline file can be written from a run and loaded later

---

## Task 18 — Diff engine (run vs baseline) + threshold checks

**Goal:** Fail CI when regressions exceed configured thresholds.

**Implement threshold config:**

* `min_success_rate` (absolute)
* `max_avg_wall_ms_delta_pct` (percentage increase allowed)
* `max_p95_wall_ms_delta_pct`

**Acceptance criteria:**

* If baseline success_rate is 1.0 and current is 0.8, suite fails with clear diff summary
* Diff summary appears in summary.json and printed to console

---

## Task 19 — CLI commands: `diff` + `baseline promote`

**Goal:** Explicit workflows for baseline management.

**Commands:**

* `cli diff --baseline <path> --run <run_dir>`
* `cli baseline promote --from <run_dir> --to <baseline_path>`

**Acceptance criteria:**

* Promote copies/creates baseline with correct schema_version and metrics
* Diff prints a human-readable regression report

---

# Phase 4 — Record mode + tool registry (local authoring workflow)

## Task 20 — Tool registry interface + built-in mock tools

**Goal:** Enable live tool execution in record mode while staying framework-agnostic.

**Codex should:**

* Define `Tool` interface in runner:

  * `name: str`
  * `call(args: dict) -> dict`
* Load tools from a Python module path (simple plugin)
* Provide a built-in `mock_search_docs` tool for demos

**Acceptance criteria:**

* Runner can execute tools in live/record mode without any external services

---

## Task 21 — Record mode: write cassette entries deterministically

**Goal:** Record tool results for later replay.

**Implement:**

* On each tool_call in record mode:

  * call tool
  * respond tool_result
  * append cassette entry (JSONL)
* Ensure canonical args are stored as the exact args received

**Acceptance criteria:**

* Running in record creates cassette file
* Switching to replay uses that cassette and yields same results

---

# Phase 5 — HTML report (static, shareable)

## Task 22 — Report data model + Jinja2 report.html

**Goal:** A single static HTML that debugs failures and sells the tool.

**Must show:**

* suite overview + pass/fail + regressions summary
* per-case table with filters
* per-case trace viewer (tool calls/results/final output)
* failure messages (assertion + budget + replay mismatch)

**Acceptance criteria:**

* `report.html` opens locally without a server and renders key information

---

# Phase 6 — GitHub Action (adoption)

## Task 23 — Composite GitHub Action

**Goal:** One snippet runs in PR CI, uploads artifacts, and gates merges.

**Action should:**

* install CLI
* run suites (default replay)
* upload artifacts: report.html, summary.json, junit.xml
* set non-zero exit code on regression

**Acceptance criteria:**

* Demo repo PR shows failing check on regression and attaches artifacts

---

# Cross-cutting hardening tasks (do alongside phases)

## Task 24 — Redaction + secret scanning in artifacts

**Goal:** Prevent accidental secret leakage.

**Codex should:**

* Implement redaction utility:

  * redact keys list (`api_key`, `token`, `authorization`, etc.)
  * regex patterns for common secrets
* Apply redaction to:

  * run.jsonl
  * summary.json
  * cassette writes (record mode)

**Acceptance criteria:**

* If input contains `api_key`, artifacts show `[REDACTED]`

---

## Task 25 — Golden-file tests for artifact stability

**Goal:** Keep output formats stable.

**Codex should:**

* Generate golden expected `summary.json` + `junit.xml` for demo
* Assert structure and key fields remain stable across refactors

**Acceptance criteria:**

* Tests fail if artifact formats unintentionally change

---

# Execution order for Codex (recommended PR sequence)

1. Tasks **1–3** (scaffold + config loading)
2. Tasks **4–6** (protocol + canonicalization)
3. Tasks **5, 7–8** (subprocess + cassette replay + runner)
4. Tasks **9–11** (assertions + artifacts + CLI run)
5. Tasks **12–13** (example agent + integration tests)
6. Then Phase 2/3/4/5/6 in order.






