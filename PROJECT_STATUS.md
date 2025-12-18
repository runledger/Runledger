# RunLedger Project Status

## Summary
- Core engine is complete with replay/record, assertions, budgets, baselines, diffs, report, and tests.
- `runledger init` now generates a replay-ready suite, cassette, baseline, and agent stub.
- This repo has CI + badges; PyPI `0.1.0` is published; action tag `v0.1` is available.
- Demo repo is published (`runledger/runledger-demo`) with regression branches and CI running on all branches.
- Release workflow is live and published `v0.1.0`.

## Deliverable status (v0.1 launch quality)
- Deliverable 1 (init + green run): ✅ complete; clean venv + PyPI verification passed.
- Deliverable 2 (killer demo repo): ✅ repo + regression branches published; CI runs on all branches.
- Deliverable 3 (release): ✅ v0.1.0 published to PyPI, action tagged v0.1; clean install verified.
- Deliverable 4 (dogfood CI): ✅ workflows in place and running on org.

## Next steps
- Add README GIF/screenshot + optional CI badge in demo repo.
- Optional: expand templates (Node/TS) and richer budgets when agents report tokens/cost.

---

# Deliverable 1: `runledger init` that gets a green run in minutes

## Goal

A brand-new user runs:

```bash
runledger init
runledger run ./evals/demo --mode replay --baseline ./baselines/demo.json
```

...and it passes on the first try.

## Checklist

- [x] CLI UX
  - [x] `runledger init` creates `./evals/demo` and `./baselines/demo.json` by default
  - [x] Flags: `--path`, `--suite`, `--template`, `--force`
  - [x] `--language python` supported (python only in v0.1)
- [x] Template output (python)
  - [x] `evals/demo/suite.yaml`
  - [x] `evals/demo/schema.json`
  - [x] `evals/demo/cases/t1.yaml`
  - [x] `evals/demo/cassettes/t1.jsonl`
  - [x] `evals/demo/agent/agent.py`
  - [x] `baselines/demo.json`
- [x] Template rules
  - [x] Suite defaults to replay mode
  - [x] Cassette matches the stub agent tool call
  - [x] Baseline exists and does not false-fail on different machines
- [x] Post-init instructions printed with next commands
- [x] Verified in a clean venv with `pip install <local path>` (WSL)
- [ ] Verify `pipx install runledger==0.1.0` after PyPI release

## Acceptance criteria

- [x] Fresh directory, `runledger init` succeeds
- [x] `runledger run ./evals/demo --mode replay --baseline baselines/demo.json` passes
- [x] Editing `schema.json` to require a new field fails
- [x] Editing `agent.py` to call a different tool/args fails with a cassette mismatch

---

# Deliverable 2: "Killer demo" repo with regression branches

## Goal

Anyone can watch CI fail for three real reasons without reading docs.

## Checklist

- [x] Scaffold exists under `demo_repo/` using the `init` output
- [x] CI workflow in the scaffold runs replay mode and uploads artifacts
- [x] Regression templates added under `demo_repo/regressions/`
- [ ] Publish a separate demo repo
- [ ] Add regression branches:
  - [ ] `regression-schema` (JSONSchema failure)
  - [ ] `regression-tools` (tool contract failure or allowlist failure)
  - [ ] `regression-budget` (budget or regression threshold failure)
- [ ] Add README GIF or screenshot of a failing PR

## Acceptance criteria

- [ ] `main` branch CI green
- [ ] Each regression branch CI red with a clear reason in:
  - [ ] GitHub check output
  - [ ] `junit.xml`
  - [ ] `summary.json`
  - [ ] `report.html`

---

# Deliverable 3: v0.1.0 release (PyPI + tagged action)

## Goal

People can depend on it like a real tool.

## Checklist

- [x] Version set to `0.1.0` in `pyproject.toml`
- [x] `CHANGELOG.md` added
- [x] Release workflow added with release notes and demo repo link
- [ ] Tag `v0.1.0` and publish to PyPI
- [ ] Tag the GitHub Action (`@v0.1.0` or `@v0.1`)
- [ ] Verify in a clean env:
  - [ ] `pipx install runledger==0.1.0`
  - [ ] `runledger init` works

## Acceptance criteria

- [ ] A user can install from PyPI and run init + replay without cloning the repo
- [ ] The GitHub Action works when referenced by tag

---

# Deliverable 4: Dogfood CI in the main RunLedger repo

## Goal

This repo proves the product.

## Checklist

- [x] Workflow runs pytest and the demo suite in replay mode
- [x] Artifacts are uploaded (`run.jsonl`, `summary.json`, `junit.xml`, `report.html`)
- [x] README badges added (CI, PyPI, license)
- [ ] Confirm CI run green on GitHub

## Acceptance criteria

- [ ] Every PR runs RunLedger on itself and produces artifacts
- [ ] CI failures are readable without local repro

---

## Current behavior

- Outputs are written under `runledger_out/<suite>/<run_id>`.
- Baselines live under `baselines/<suite>.json`.
- Demo suite runs via `runledger run examples/evals/demo --mode replay`.
- HTML report is generated automatically with each run.

## Positioning

- Tool-call determinism over model-graded vibes: record once, replay in CI, fail on mismatch.
- Tool schemas, allowlists, and ordering are enforced as contracts.
- CI-native UX is the product: exit codes, JUnit, GitHub Checks, baseline diffs, no dashboard required.
- Language-agnostic agent protocol (JSONL subprocess) for Python/Node/Go parity.
- Budgets are gates, not metrics: p95 latency/tool errors/tool calls are regression criteria.

## Current competition (how people solve agent quality today)

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

## How we stand out (defensible wedge)

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

4. Budgets are product, not a metric
   - "Works but costs 3x" is a regression.
   - Gating on p95 latency/tool errors/tool call count is a business requirement, not a nice-to-have.

## Standout playbook (what to ship/market next)

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

## Where we will not win (so we do not waste time)

- Competing head-on with LangSmith/Braintrust/Phoenix/Langfuse/Weave on dashboards, dataset UIs, and production monitoring.
- Trying to be "the best LLM judge" or "the most metrics".

## Simple differentiation statement

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

## Optional next steps

- Publish the demo repo and regression branches.
- Ship the PyPI release and tag the GitHub Action.
- Expand templates to Node/TS once v0.1 is stable.
- Add richer budget metrics when agents report tokens/cost.
