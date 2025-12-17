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

```bash
pytest
```

## Style

- Keep changes focused and add tests when behavior changes.
