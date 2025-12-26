# Changelog

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
