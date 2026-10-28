"""Read-only suite diagnostics. This module never starts or imports an agent."""

from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from pydantic import ValidationError

from runledger.baseline.io import load_baseline
from runledger.cassette.loader import load_cassette
from runledger.config.loader import load_cases, load_suite
from runledger.runner.subprocess import resolve_agent_command


def _add(
    checks: list[dict[str, Any]], name: str, status: str, message: str, **details: Any
) -> None:
    checks.append({"name": name, "status": status, "message": message, **details})


def _configuration_error(exc: Exception) -> str:
    # Parser and Pydantic exception strings can contain code, arguments, or secrets.
    if isinstance(exc, ValidationError):
        fields = sorted({str(error["loc"][0]) for error in exc.errors() if error["loc"]})
        return "Invalid configuration; check field(s): " + ", ".join(fields)
    cause = exc.__cause__
    if isinstance(cause, yaml.YAMLError):
        mark = getattr(cause, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        return f"Invalid YAML{location}."
    if isinstance(exc, (OSError, UnicodeError)):
        return "A required configuration file or directory is missing or unreadable as UTF-8."
    return "Invalid configuration; expected a YAML mapping with the documented fields."


def _script_argument(command: list[str]) -> str | None:
    """Recognize common interpreter script positions, without guessing opaque argv."""
    program = Path(command[0]).name.lower().removesuffix(".exe")
    is_python = program.startswith("python")
    if not is_python and program not in {"node", "nodejs", "bash", "sh", "ruby", "perl"}:
        return None
    index = 1
    while index < len(command):
        value = command[index]
        if value == "--":
            return command[index + 1] if index + 1 < len(command) else None
        if value in {"-c", "-e", "--eval", "-p", "--print", "-m"}:
            return None
        if is_python and value in {"-W", "-X"}:
            index += 2
            continue
        if is_python and value.startswith(("-W", "-X")):
            index += 1
            continue
        if is_python and value in {
            "-u",
            "-B",
            "-O",
            "-OO",
            "-S",
            "-s",
            "-E",
            "-I",
            "-q",
            "-i",
            "-v",
            "-x",
        }:
            index += 1
            continue
        if value.startswith("-"):
            return None
        return value
    return None


def _executable_file(path: str) -> bool:
    candidate = Path(path)
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        return False
    if os.name == "nt" and candidate.suffix.lower() not in {".bat", ".cmd"}:
        # X_OK and which can accept .py via PATHEXT/file associations, but
        # Popen(shell=False) needs a native executable or a batch script.
        with candidate.open("rb") as stream:
            return stream.read(2) == b"MZ"
    return True


def _check_command(command: list[str], checks: list[dict[str, Any]]) -> None:
    if not command or not command[0].strip() or any("\x00" in value for value in command):
        _add(checks, "agent_executable", "fail", "agent_command is empty or contains a null byte.")
        return
    try:
        resolved = resolve_agent_command(command)
        program = resolved[0]
        executable = shutil.which(program)
        if executable is None or not _executable_file(executable):
            _add(
                checks,
                "agent_executable",
                "fail",
                "Agent executable is missing or not executable; check agent_command[0] and PATH, and launch script files through their interpreter.",
            )
        else:
            _add(
                checks,
                "agent_executable",
                "pass",
                "Agent executable is available.",
                path=executable,
            )
        script = _script_argument(resolved)
        if script is not None:
            path = Path(script)
            if not path.is_absolute():
                path = Path.cwd() / path
            if not path.is_file():
                _add(
                    checks,
                    "agent_script",
                    "fail",
                    "The interpreter's script argument is missing or is not a file; paths left relative by the loader use the current working directory.",
                )
            else:
                _add(
                    checks,
                    "agent_script",
                    "pass",
                    "The interpreter's script file exists.",
                    path=str(path),
                )
    except (OSError, ValueError):
        _add(
            checks,
            "agent_executable",
            "fail",
            "Agent executable or script path cannot be inspected.",
        )


def _check_budgets(raw: dict[str, Any], scope: str, checks: list[dict[str, Any]]) -> None:
    budgets = raw.get("budgets")
    if not isinstance(budgets, dict):
        return
    for field, value in budgets.items():
        if value is None:
            continue
        try:
            numeric = float(value)
            valid = not isinstance(value, bool) and math.isfinite(numeric) and numeric >= 0
            if field != "max_cost_usd":
                valid = valid and numeric.is_integer()
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            _add(
                checks,
                "budgets",
                "fail",
                "Budget limits must be finite, nonnegative numbers; count and time limits must be integers.",
                scope=scope,
                field=field,
            )
        elif field in {"max_tokens_out", "max_cost_usd"}:
            _add(
                checks,
                "budgets",
                "warning",
                "This token or cost budget is configured but is not enforced by the current runner.",
                scope=scope,
                field=field,
            )
        else:
            _add(checks, "budgets", "pass", "Budget limit is valid.", scope=scope, field=field)


def _has_external_reference(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                key in {"$ref", "$dynamicRef"}
                and isinstance(item, str)
                and not item.startswith("#")
            ):
                return True
            if _has_external_reference(item):
                return True
    elif isinstance(value, list):
        return any(_has_external_reference(item) for item in value)
    return False


def _check_assertions(
    assertions: Any, scope: str, registry: set[str], checks: list[dict[str, Any]]
) -> None:
    shapes = {
        "required_fields": "fields",
        "must_call": "tools",
        "must_not_call": "tools",
        "call_order": "order",
        "json_schema": "schema_path",
    }
    for index, model in enumerate(assertions or []):
        spec = model.model_dump()
        kind = spec["type"]
        details = {"scope": scope, "assertion_index": index}
        field = shapes.get(kind)
        if field is None:
            _add(
                checks,
                "assertion",
                "fail",
                "Unsupported assertion type; supported types are json_schema, required_fields, must_call, must_not_call, and call_order.",
                **details,
            )
            continue
        value = spec.get(field)
        if kind == "json_schema":
            if not isinstance(value, str) or not value:
                _add(
                    checks,
                    "json_schema",
                    "fail",
                    "json_schema requires a nonempty schema_path.",
                    **details,
                )
                continue
            try:
                schema = json.loads(Path(value).read_text(encoding="utf-8"))
                jsonschema.Draft202012Validator.check_schema(schema)
            except (OSError, UnicodeError, ValueError, jsonschema.SchemaError):
                _add(
                    checks,
                    "json_schema",
                    "fail",
                    "Schema is missing, unreadable, invalid JSON, or invalid Draft 2020-12 JSON Schema.",
                    **details,
                )
                continue
            _add(
                checks,
                "json_schema",
                "pass",
                "Schema file is valid Draft 2020-12 JSON Schema.",
                path=value,
                **details,
            )
            if _has_external_reference(schema):
                _add(
                    checks,
                    "schema_references",
                    "warning",
                    "Schema has external references; doctor does not fetch or resolve those resources.",
                    **details,
                )
        elif not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            _add(
                checks,
                "assertion",
                "fail",
                f"{kind} requires {field} to be a list of strings.",
                **details,
            )
        elif not value:
            _add(
                checks,
                "assertion",
                "warning",
                f"{kind} has an empty {field} list and cannot catch a regression.",
                **details,
            )
        elif kind in {"must_call", "call_order"} and not set(value).issubset(registry):
            _add(
                checks,
                "assertion",
                "fail",
                "A required tool is absent from tool_registry, so this contract cannot pass.",
                **details,
            )
        else:
            _add(checks, "assertion", "pass", f"{kind} assertion has a supported shape.", **details)
        if set(spec) - {"type", field}:
            _add(
                checks,
                "assertion_fields",
                "warning",
                "This assertion has extra fields that the runner ignores.",
                **details,
            )


def doctor_suite(path: Path) -> dict[str, Any]:
    """Check local suite files without running agents, importing tools, or writing files.

    A successful result establishes static readiness only. Agent dependencies and
    protocol behavior require an explicitly requested execution probe.
    """
    suite_path = Path(path).resolve()
    if suite_path.is_dir():
        suite_path = suite_path / "suite.yaml"
    checks: list[dict[str, Any]] = []
    result = {"schema_version": 1, "ok": False, "suite_path": str(suite_path), "checks": checks}
    _add(
        checks,
        "dependency_readiness",
        "warning",
        "Static checks do not execute the agent or import user tool modules. Arbitrary agent dependencies, credentials, network isolation, and protocol behavior are unverified; use an explicit execution probe to test a case.",
    )
    try:
        suite = load_suite(suite_path)
    except (OSError, ValueError) as exc:
        _add(checks, "suite_config", "fail", _configuration_error(exc))
        return result
    _add(checks, "suite_config", "pass", "Suite configuration parses successfully.")
    _check_command(suite.agent_command, checks)
    raw_suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    _check_budgets(raw_suite, "suite", checks)
    registry = set(suite.tool_registry)
    _check_assertions(suite.assertions, "suite", registry, checks)
    if suite.regression is not None:
        for field, value in suite.regression.model_dump().items():
            if value is not None and (
                not math.isfinite(value) or (field == "min_pass_rate" and not 0 <= value <= 1)
            ):
                _add(
                    checks,
                    "regression",
                    "fail",
                    "Regression thresholds must be finite; min_pass_rate must be between 0 and 1.",
                    field=field,
                )
    if suite.baseline_path:
        try:
            baseline = load_baseline(Path(suite.baseline_path))
        except (OSError, ValueError):
            _add(
                checks,
                "baseline",
                "fail",
                "Configured baseline is missing, unreadable, or not a valid RunLedger summary.",
            )
        else:
            _add(
                checks,
                "baseline",
                "pass",
                "Configured baseline is readable and structurally valid.",
                path=suite.baseline_path,
            )
            if baseline.suite.name != suite.suite_name:
                _add(
                    checks,
                    "baseline_suite",
                    "warning",
                    "Baseline suite name differs from the current suite.",
                )
    try:
        cases = load_cases(suite_path.parent, suite.cases_path)
    except (OSError, ValueError) as exc:
        _add(checks, "case_configs", "fail", _configuration_error(exc))
        result["ok"] = False
        return result
    _add(
        checks,
        "case_configs",
        "pass",
        f"Loaded {len(cases)} case configuration(s).",
        count=len(cases),
    )
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        _add(
            checks,
            "case_ids",
            "fail",
            "Case IDs must be unique; duplicate IDs make case selection and reports ambiguous.",
        )
    else:
        _add(checks, "case_ids", "pass", "Case IDs are unique.")
    case_files = sorted((suite_path.parent / suite.cases_path).resolve().glob("*.yaml"))
    for case, case_file in zip(cases, case_files):
        scope = str(case_file)
        _check_budgets(yaml.safe_load(case_file.read_text(encoding="utf-8")), scope, checks)
        _check_assertions(case.assertions, scope, registry, checks)
        cassette_path = Path(case.cassette)
        if suite.mode != "replay" and not cassette_path.exists():
            _add(
                checks,
                "cassette",
                "warning",
                "Cassette does not exist yet; this is allowed in live/record mode but replay requires it.",
                scope=scope,
            )
            continue
        try:
            entries = load_cassette(cassette_path)
        except (OSError, ValueError):
            _add(
                checks,
                "cassette",
                "fail",
                "Cassette is missing, unreadable, or contains malformed JSONL entries; each entry needs tool (string), args (object), and ok (boolean).",
                scope=scope,
            )
            continue
        if any(entry.tool not in registry for entry in entries):
            _add(
                checks,
                "cassette",
                "fail",
                "Cassette contains a tool absent from tool_registry.",
                scope=scope,
            )
        else:
            _add(
                checks,
                "cassette",
                "pass",
                f"Cassette is readable with {len(entries)} valid entries and registered tools.",
                scope=scope,
                entries=len(entries),
            )
    result["ok"] = not any(check["status"] == "fail" for check in checks)
    return result
