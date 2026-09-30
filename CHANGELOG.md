# Changelog

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
