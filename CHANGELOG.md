# Changelog

## [0.2.4] - 2026-10-27

### Fixed

- HTML reports render agent and tool output as text, preventing script injection through traces, case IDs, and failure messages.
- Wall-time budgets interrupt agent waits, blocked writes, tool imports, and live tool calls. Tool-call limits stop excess calls before execution, and tool-error limits stop further execution immediately.
- Repeated identical tool requests consume their matching cassette entries in recorded order. An extra request now fails with a cassette mismatch rather than reusing an earlier response.
- JUnit includes failed baseline regression gates and redacts failure messages.
- Inline agent code and its arguments retain literal backslashes. Unknown regression threshold names are rejected instead of silently disabling a gate.
- Windows protocol pipes use UTF-8, Python launcher aliases work in both directions, and child processes are cleaned up even when their parent has already exited.

### Changed

- Record/live tool modules now run in a cancellable worker per case. State persists between calls within a case and resets between cases. Existing cassette files remain readable, but suites that depended on reusing one recorded response must record one entry per call.
- Documentation distinguishes recorded protocol calls from independent model/network calls made by the agent.

### Added

- A runnable, pinned `mcp-agent` integration with a fixed model fixture, ten unchanged replay checks, and three deliberate regression scenarios.
- Ubuntu/Windows CI, Python 3.9 compatibility coverage, DOM security tests, and clean-install verification of published releases.
- A developer trial guide and structured acceptance output for testing before outreach.

## [0.2.3] - 2026-10-27

### Fixed

- Secret redaction matches OpenAI (`sk-`), GitHub (`ghp_`), AWS (`AKIA`), and JWT values. The patterns were stored with a doubled backslash, so they never matched.
- Suite paths written with Windows separators (`agent\agent.py`, `cassettes\t1.jsonl`, `baseline_path`) resolve on Linux CI.
- Invalid YAML errors include the parser message.
- A suite whose `agent_command` is bare `python` runs with `python3` when `python` is not on `PATH`. The checked-in demo suite uses `python3`.
- `required_fields` failure output names the required fields instead of calling them present.
- The composite action writes `result`, `exit-code`, and `artifacts-path` in a step that succeeds, then fails the job from a later step, so callers can read those outputs when the run fails. Docs and the quickstart pin `runledger/Runledger@v0.2.3` (the `v0.2` tag still points at the 0.2.1 action, which does not set outputs).
- README, `summary.md`, and the quickstart describe only the gates the runner enforces: JSON Schema, required fields, tool order (`must_call`, `must_not_call`, `call_order`), and `max_wall_ms` / `max_tool_calls` / `max_tool_errors`.

### Added

- `runledger init` writes `.github/workflows/runledger.yml` next to the eval suite and baseline. A second run leaves existing scaffold files unchanged. `--force` regenerates the suite, baseline, and workflow.
- The init demo gates on JSON Schema (`schema.json`), tool order (`call_order: [search_docs]`), and tool-call budget (`max_tool_calls: 1`).
- Root action outputs: `result` (`pass` or `fail`), `exit-code`, and `artifacts-path`. Optional `baseline` input. `.github/workflows/action-self-test.yml` runs the action with `uses: ./`.
- Five-minute quickstart at the top of the README and in `docs/site-quickstart.md`.

### Changed

- Action name stays `RunLedger`. A Marketplace search on 2026-10-27 returned no listing with that name, and the `runledger` organization owns the name.
- Action `path` default is `./evals/demo`, matching `runledger init`.

## [0.2.2] - 2026-10-08

### Fixed

- `runledger init` no longer hardcodes `python` as the generated agent command. It uses
  `python3` when that executable is on `PATH`, then `python`, then the interpreter running
  RunLedger (`sys.executable`). The README quickstart works on Ubuntu, macOS, and pipx
  installs where only `python3` exists.
- A missing or unrunnable `agent_command` is reported as an actionable error (what was
  missing, and how to set `agent_command` in `suite.yaml`) instead of a raw Python traceback.
  `runledger init` also refuses to write a baseline when the example agent does not pass.

### Added

- Package metadata project URLs so the PyPI page links to the homepage (https://runledger.io),
  the GitHub repository, the docs, and the changelog.

### Changed

- README demo link now points at https://github.com/ZackMitchell910/runledger-demo/pull/1,
  which is left open to show RunLedger failing a bad agent change.

## [0.2.1] - 2026-09-30

### Added

- `runledger run` now explains failures on the console. After the results table it prints a
  block for every failing case with the case id, assertion type, message, and (where the
  assertion records them) expected vs. observed values, e.g. for `call_order`:
  `Tool call order not satisfied: lookup_order -> issue_refund` with the expected and observed
  tool sequences. Budget failures (`max_tool_calls`, `max_tool_errors`, `max_wall_ms`), runtime
  failures (tool not allowed, cassette mismatch, task/agent errors), and failing regression
  gates (e.g. `min_pass_rate`) are reported the same way.
- When `GITHUB_ACTIONS=true`, each failure is also emitted as a GitHub Actions annotation:
  `::error title=runledger: <case>::<message>` (gates use `title=runledger: gate <id>`).

### Changed

- No change to exit codes, artifacts, or which checks are enforced; the new output is derived
  from data already recorded in `run.jsonl` / `summary.json`.

## [0.2.0] - 2026-09-30

### Added

- Output normalization: new `normalization` block in `suite.yaml` and per-case config
  (`strip_keys`, `strip_paths`, `replace_paths`, `replace_text` with regex flags). Applied to
  tool results/errors before recording and to final output before assertions, so volatile
  values (timestamps, IDs, seeds) no longer break replay or baselines.
- `runledger init --language node` generates a Node.js agent template (`agent/agent.js`);
  requires `node` on `PATH`.

### Fixed

- Portable baselines/artifacts: `summary.json` and regression output now record
  cwd-relative, POSIX-style paths for `suite_path`, `agent_command`, cassette paths, and
  `baseline_path` instead of machine-specific absolute paths.
- `runledger baseline promote` strips the `regression` block from the promoted summary and
  recomputes `run.exit_status` from case results.
- `runledger init` prints relative paths and emits a CI snippet that includes `--baseline`;
  generated Python agent now exits with a proper status code.
- Python 3.9 support: added `eval_type_backport` (Python < 3.10 only) so pydantic models using
  `X | None` annotations load on 3.9 (previously every command failed on 3.9).
- Fixed an over-escaped regex in the `replace_text` normalization test.

### Changed

- Demo suite regression thresholds stabilized; demo baselines regenerated.
- CI and release workflows can be triggered manually (`workflow_dispatch`; release takes a `tag` input).
- Docs: README no longer claims token/cost budgets or cost-regression gates are enforced
  (only `max_wall_ms`, `max_tool_calls`, `max_tool_errors` fail runs today). README tightened, new `docs/integrations.md`, quickstart updates; Action usage now
  points to `runledger/Runledger@v0.2`.
- Packaging: SPDX `license = "MIT"` + `license-files` (clears setuptools deprecation); build
  requires `setuptools>=77`; dropped redundant `wheel` build requirement.

## [0.1.1] - 2025-12-26

### Changed

- GitHub Action now includes Marketplace branding metadata.
- `pytest` config avoids collecting tests in `automation/workdir/` clones.
- Docs: composite action usage points to `runledger/Runledger@v0.1`; release notes link to the demo repo.

## [0.1.0] - 2025-12-17

### Added

- Deterministic record/replay harness for tool-using agents.
- CLI commands: `run`, `diff`, `baseline promote`, and `init`.
- Assertions for JSON schema, required fields, and tool contracts.
- Budget enforcement and regression gating vs baselines.
- Artifact outputs: `run.jsonl`, `summary.json`, `junit.xml`, `report.html`.
- Composite GitHub Action for CI usage.
