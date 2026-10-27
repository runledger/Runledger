from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .models import CaseConfig, SuiteConfig

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def normalize_config_path(value: str) -> str:
    """Turn Windows separators into POSIX separators.

    Suites authored on Windows often store ``agent\\agent.py`` and
    ``cassettes\\t1.jsonl``. Those strings do not resolve on the Linux runners
    used by GitHub Actions. Forward slashes work on both.
    """
    if "\\" not in value:
        return value
    return value.replace("\\", "/")


def _is_absolute_config_path(value: str) -> bool:
    if Path(value).is_absolute():
        return True
    return bool(_WINDOWS_DRIVE.match(value)) or value.startswith("//")


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        detail = str(exc).strip() or "could not parse the file"
        raise ValueError(f"Invalid YAML in {path}: {detail}") from exc
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
        if isinstance(schema_path, str):
            schema_path = normalize_config_path(schema_path)
            if not _is_absolute_config_path(schema_path):
                schema_path = str((base_dir / schema_path).resolve())
            entry["schema_path"] = schema_path


def load_suite(path: Path) -> SuiteConfig:
    suite_path = path
    if suite_path.is_dir():
        suite_path = suite_path / "suite.yaml"
    if not suite_path.is_file():
        raise FileNotFoundError(f"Suite file not found: {suite_path}")
    data = _load_yaml(suite_path)
    cases_path = data.get("cases_path")
    if isinstance(cases_path, str):
        data["cases_path"] = normalize_config_path(cases_path)
    agent_command = data.get("agent_command")
    if isinstance(agent_command, list):
        resolved_command: list[object] = []
        for part in agent_command:
            if isinstance(part, str):
                part = normalize_config_path(part)
                if not _is_absolute_config_path(part):
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
    if isinstance(baseline_path, str):
        baseline_path = normalize_config_path(baseline_path)
        if not _is_absolute_config_path(baseline_path):
            baseline_path = str((suite_path.parent / baseline_path).resolve())
        data["baseline_path"] = baseline_path
    output_dir = data.get("output_dir")
    if isinstance(output_dir, str):
        output_dir = normalize_config_path(output_dir)
        if not _is_absolute_config_path(output_dir):
            output_dir = str((suite_path.parent / output_dir).resolve())
        data["output_dir"] = output_dir
    return SuiteConfig.model_validate(data)


def load_cases(suite_dir: Path, cases_path: str) -> list[CaseConfig]:
    """Load cases with cassette paths resolved relative to the suite directory."""
    cases_path = normalize_config_path(cases_path)
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
        if isinstance(cassette_value, str):
            cassette_value = normalize_config_path(cassette_value)
            if not _is_absolute_config_path(cassette_value):
                cassette_value = str((suite_dir / cassette_value).resolve())
            data["cassette"] = cassette_value
        assertions = data.get("assertions")
        if isinstance(assertions, list):
            _resolve_schema_paths(assertions, suite_dir)
        cases.append(CaseConfig.model_validate(data))
    return cases
