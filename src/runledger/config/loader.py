from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import CaseConfig, SuiteConfig


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}") from exc
    except OSError as exc:
        raise FileNotFoundError(f"Unable to read {path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return data


def _resolve_schema_paths(assertions: list[object], base_dir: Path) -> None:
    for entry in assertions:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") != "json_schema":
            continue
        schema_path = entry.get("schema_path")
        if isinstance(schema_path, str) and not Path(schema_path).is_absolute():
            entry["schema_path"] = str((base_dir / schema_path).resolve())


def load_suite(path: Path) -> SuiteConfig:
    suite_path = path
    if suite_path.is_dir():
        suite_path = suite_path / "suite.yaml"
    if not suite_path.is_file():
        raise FileNotFoundError(f"Suite file not found: {suite_path}")
    data = _load_yaml(suite_path)
    agent_command = data.get("agent_command")
    if isinstance(agent_command, list):
        resolved_command: list[object] = []
        for part in agent_command:
            if isinstance(part, str) and not Path(part).is_absolute():
                candidate = (suite_path.parent / part).resolve()
                if candidate.exists():
                    resolved_command.append(str(candidate))
                    continue
            resolved_command.append(part)
        data["agent_command"] = resolved_command
    assertions = data.get("assertions", [])
    if isinstance(assertions, list):
        _resolve_schema_paths(assertions, suite_path.parent)
    baseline_path = data.get("baseline_path")
    if isinstance(baseline_path, str) and not Path(baseline_path).is_absolute():
        data["baseline_path"] = str((suite_path.parent / baseline_path).resolve())
    output_dir = data.get("output_dir")
    if isinstance(output_dir, str) and not Path(output_dir).is_absolute():
        data["output_dir"] = str((suite_path.parent / output_dir).resolve())
    return SuiteConfig.model_validate(data)


def load_cases(suite_dir: Path, cases_path: str) -> list[CaseConfig]:
    """Load cases with cassette paths resolved relative to the suite directory."""
    cases_dir = (suite_dir / cases_path).resolve()
    if not cases_dir.is_dir():
        raise FileNotFoundError(f"Cases directory not found: {cases_dir}")

    case_files = sorted(cases_dir.glob("*.yaml"))
    if not case_files:
        raise FileNotFoundError(f"No case files found in {cases_dir}")

    cases: list[CaseConfig] = []
    for case_file in case_files:
        data = _load_yaml(case_file)
        cassette_value = data.get("cassette")
        if isinstance(cassette_value, str) and not Path(cassette_value).is_absolute():
            data["cassette"] = str((suite_dir / cassette_value).resolve())
        assertions = data.get("assertions")
        if isinstance(assertions, list):
            _resolve_schema_paths(assertions, suite_dir)
        cases.append(CaseConfig.model_validate(data))
    return cases
