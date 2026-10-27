# Contributing

Thanks for contributing to RunLedger.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
runledger --help
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
runledger --help
```

## Tests

CI runs the test suite and the checked-in demo:

```bash
pytest
runledger run examples/evals/demo --mode replay --baseline baselines/demo.json
```

`ruff` and `mypy` are installed with the `dev` extra. The GitHub Actions workflow runs `pytest` and the demo replay, not the linters. Run `pytest` before opening a pull request.

## Docs and claims

Describe gates the runner enforces:

- output schema (`json_schema`, `required_fields`)
- tool order (`call_order`, `must_call`, `must_not_call`)
- `max_tool_calls`, `max_wall_ms`, and `max_tool_errors`

`tests/docs/test_public_claims.py` checks the public docs. Replay mode does not call a live model. Say that about replay. `record` and `live` run the configured tools.

## Pull requests

- Keep the change focused.
- Add or update tests when behavior changes.
- Do not bump the version in `pyproject.toml` or `src/runledger/__init__.py` unless you are publishing a release.

## Security

Report security issues using `SECURITY.md`.

## Code of conduct

See `CODE_OF_CONDUCT.md`.
