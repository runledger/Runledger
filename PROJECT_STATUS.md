# RunLedger Project Status

Next steps
Do this “next sprint” as four concrete deliverables. Each one is independently valuable, but together they turn RunLedger from “engine” into “adoptable product.”

Progress (this repo)
- Deliverable 1 in progress: `runledger init` now generates a replay-ready suite, cassette, baseline, and agent stub.
- Deliverable 2 in progress: demo repo scaffold added under `demo_repo/`.
- Deliverable 3 in progress: `CHANGELOG.md` and `.github/workflows/release.yml` added.
- Deliverable 4 in progress: dogfood CI workflow and README badges added.

# Deliverable 1: `runledger init` that gets a green run in minutes

## Goal

A brand-new user runs:

```bash
runledger init
runledger run ./evals --mode replay --baseline ./baselines/demo.json
```

…and it passes on the first try.

## Implementation checklist

1. **CLI UX**

* `runledger init` (default: creates `./evals/demo` + `./baselines/demo.json`)
* Flags:

  * `--path ./evals`
  * `--suite demo`
  * `--template support-triage` (default)
  * `--force` (overwrite)
  * `--language python|node` (optional; python first)

2. **Template output (python)**
   Generate these files:

```
evals/demo/
  suite.yaml
  schema.json
  cases/
    t1.yaml
  cassettes/
    t1.jsonl
  agent/
    agent.py
baselines/
  demo.json
```

3. **Template rules**

* Suite runs in **replay** by default.
* Cassette exists and matches exactly what the stub agent will call.
* Baseline exists and won’t false-fail on different machines (avoid strict latency deltas in default regression policy; gate mainly on success rate + tool-call count).

4. **Post-init instructions**
   At the end of `init`, print:

* the next 2 commands to run
* the path to `report.html` that will be generated

## Acceptance criteria

* Fresh directory, `runledger init` succeeds
* `runledger run ./evals/demo --mode replay --baseline baselines/demo.json` passes
* If user edits `schema.json` to require a new field → fail
* If user edits `agent.py` to call a different tool/args → cassette mismatch fail

---

# Deliverable 2: “Killer demo” repo with regression branches

## Goal

Anyone can watch CI fail for 3 real reasons without reading docs.

## Repo structure

* Use the exact `init` output as the repo content.
* Add `.github/workflows/ci.yml` that runs in replay mode and uploads artifacts.

## Branches (each should fail CI)

1. `regression-schema`

* Break schema: require an extra field not produced (or rename a required field).
* Expected failure: JSONSchema assertion.

2. `regression-tools`

* Change agent to:

  * call a disallowed tool, or
  * skip a required tool, or
  * violate call order.
* Expected failure: tool contract assertion or allowlist violation.

3. `regression-budget` (pick one deterministic failure)

* Increase tool calls (agent calls `search_docs` twice) while budget is `max_tool_calls: 1`, OR
* keep budgets same but configure regression policy to fail when tool_calls increases vs baseline.
* Expected failure: budget/regression gate.

## Acceptance criteria

* `main` branch CI green
* Each regression branch CI red with an obvious reason in:

  * GitHub check output
  * `junit.xml`
  * `summary.json`
  * `report.html`

---

# Deliverable 3: v0.1.0 release (PyPI + tagged action)

## Goal

People can depend on it like a real tool.

## Checklist

1. **Versioning**

* Set version to `0.1.0`
* Add `CHANGELOG.md` with “what’s included”

2. **Packaging sanity**

* Ensure templates ship in the wheel/sdist (package data)
* Verify in a clean env:

  * `pipx install runledger==0.1.0`
  * `runledger init` works

3. **GitHub Releases**

* Tag `v0.1.0`
* Release notes include quickstart + the demo repo link

4. **Action versioning**

* Make sure users can do:

  * `uses: <owner>/runledger@v0.1.0` (or `@v0.1`)
* Document the exact snippet in README.

## Acceptance criteria

* A user can install from PyPI and run init + replay without cloning your repo
* The GitHub Action works when referenced by tag

---

# Deliverable 4: Dogfood CI in the main RunLedger repo

## Goal

Your repo proves the product.

## Checklist

* Add a workflow in this repo that:

  * runs demo suite in replay mode
  * runs `pytest`
  * uploads artifacts
* Add badges to README (CI, PyPI, license)

## Acceptance criteria

* Every PR runs RunLedger on itself and produces artifacts
* CI failures are readable without local repro

---

## Recommended PR sequence (now that core is done)

1. PR: **`init` command + bundled templates + smoke test**
2. PR: **in-repo CI workflow dogfooding RunLedger**
3. PR: **release workflow + v0.1.0 polish (changelog, docs, packaging)**
4. Separate repo: **killer demo repo + regression branches + README GIF**

If you paste your current repo tree (top-level folders + where `action.yml` lives + where CLI commands are defined), I’ll map this into an exact PR-by-PR file list with the concrete template contents (suite.yaml/case/cassette/agent/baseline) matching your current schema keys.

## Positioning

- Tool-call determinism over model-graded vibes: record once, replay in CI, fail on mismatch.
- Tool schemas, allowlists, and ordering are enforced as contracts.
- CI-native UX is the product: exit codes, JUnit, GitHub Checks, baseline diffs, no dashboard required.
- Language-agnostic agent protocol (JSONL subprocess) for Python/Node/Go parity.
- Budgets are gates, not metrics: p95 latency/tool errors/tool calls are regression criteria.

## Current Competition (How People Solve "Agent Quality" Today)

### 1) Prompt/LLM test runners (CI-friendly)

- Promptfoo: config-driven evals with assertions; designed to run in CI/CD.
- DeepEval (Confident AI): "pytest for LLMs", heavy on metrics (often LLM-as-judge) and test-style workflows.

What they are great at: prompt/model comparisons, dataset-driven scoring, fast iteration in dev, some CI gating.
Where they can fall short for agents: multi-step tool-using behavior, tool contract enforcement, and deterministic replay as the primary wedge (our lane).

### 2) Evals + tracing platforms (workflow + UI + datasets)

- LangSmith: evals across lifecycle; includes regression testing concepts and cost/latency/quality monitoring.
- Braintrust: evaluation workflows + comparing traces/runs, iteration loops.

What they are great at: visibility, iteration, dataset management, comparing runs; often a platform-centric workflow.

### 3) Observability-first (open source, OTel-based) with eval features

- Arize Phoenix: open-source tracing + evaluation, OTel-native.
- Langfuse: open-source observability/tracing with evaluation concepts.
- W&B Weave: tracing + evaluation workflows.
- TruLens: evals + tracing with feedback functions.

What they are great at: "what happened?" in dev/prod; instrumentation, traces, scoring.

## How We Stand Out (Defensible Wedge)

Our product wins if we own this sentence:

> "CI merge gates for tool-using agents via deterministic tool replay + hard contracts (schema/tool/budgets)."

Concretely, we stand out by being the best at:

1. Tool-call determinism, not model-graded vibes
   - Record tool interactions once, replay in CI, fail on mismatch.
   - Treat tool schemas/ordering/allowlists as first-class contracts.

2. CI-native gating as the primary UX
   - Exit codes, JUnit, GitHub Checks, baseline diffs - no dashboard required.
   - Promptfoo explicitly markets CI/CD integration; we go deeper on agent regression gates than "LLM evals in CI."

3. Language-agnostic agent protocol
   - Any agent (Python/Node/Go) can be tested the same way via subprocess JSONL.
   - This separates us from platform- or framework-coupled workflows.

4. Budgets as product, not a metric
   - "Works but costs 3x" is a regression.
   - Gating on p95 latency/tool errors/tool call count is a business requirement, not a nice-to-have.

## Standout Playbook (What To Ship/Market Next)

### A) Positioning (keep it narrow and sharp)

- Do not call it "observability" or "evaluation platform".
- Call it "CI for agents" / "merge gates for agents" / "contract tests for agents".

### B) Make the demo unavoidable (growth engine)

- Ship a demo repo with three PRs that fail for different reasons:
  - schema regression (JSONSchema fails)
  - tool regression (must-call / must-not-call / call-order fails)
  - budget regression (tool calls or p95 latency increases)

### C) Win on tool contracts (competitors under-emphasize this)

- Tool allowlist + tool schema validation
- must-call / must-not-call / call-order checks
- "no network" in CI (enforce replay mode by default)
- cassette mismatch diagnostics that are actually readable

### D) Adoptability: 10-minute green run

- `init` creates suite + stub agent + cassette
- GitHub Action snippet works on first try
- JUnit shows failures in the PR UI

## Where We Won't Win (So We Don't Waste Time)

- Competing head-on with LangSmith/Braintrust/Phoenix/Langfuse/Weave on dashboards, dataset UIs, and production monitoring.
- Trying to be "the best LLM judge" or "the most metrics".

## Simple Differentiation Statement

"Prompt eval tools tell you if outputs look good. Observability tools tell you what happened. We block merges when an agent's tool-using behavior, schemas, or budgets regress - deterministically - using record/replay."

## Completed

- Core CLI implemented (`runledger run`, `runledger diff`, `runledger baseline promote`).
- Suite and case configuration via YAML with schema path resolution.
- Protocol JSONL messaging with strict stdout parsing and stderr logging.
- Deterministic replay with cassettes and exact tool-call matching.
- Record/live tool execution with a registry and built-in mock tools.
- Assertions (json_schema, required_fields, tool contracts) and budget enforcement.
- Baseline schema v1 and regression checks with thresholds and reporting.
- Artifact outputs: `run.jsonl`, `summary.json`, `junit.xml`, `report.html`.
- Redaction of sensitive fields in artifacts and cassette writes.
- Demo agent + demo eval suite + baseline (`baselines/demo.json`).
- Comprehensive tests including integration and golden artifact files.
- Composite GitHub Action (`action.yml`) for CI runs and artifact upload.

## Current Behavior

- Outputs are written under `runledger_out/<suite>/<run_id>`.
- Baselines live under `baselines/<suite>.json`.
- Demo suite runs via `runledger run examples/evals/demo --mode replay`.
- HTML report is generated automatically with each run.

## What To Continue Implementing (Optional Next Steps)

- Implement `runledger init` templates (currently a stub).
- Ship a "killer demo" repo with regression branches and a README GIF.
- Add richer tool plugins and documentation for custom tool modules.
- Expand metrics/budgets for tokens and cost when agents provide them.
- Harden redaction patterns based on real data and audit needs.
- Improve HTML report (more filtering, metrics charts, trace search).
- Add CI workflow in-repo that uses the composite action.
- Publish and version releases to PyPI and tag GitHub releases.
