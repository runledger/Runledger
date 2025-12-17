from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from .base import AssertionFailure


def apply_json_schema(output: dict[str, Any], schema_path: str) -> list[AssertionFailure]:
    try:
        resolved = Path(schema_path)
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve()
        schema = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:
        return [
            AssertionFailure(
                type="json_schema_error",
                message=f"Failed to load schema {schema_path}: {exc}",
            )
        ]

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(output), key=lambda err: list(err.path))
    if not errors:
        return []

    first = errors[0]
    path = "/".join(str(part) for part in first.path) or "<root>"
    details: dict[str, object] = {"path": path, "error": first.message}
    if first.validator == "required" and isinstance(first.validator_value, list):
        missing = []
        if isinstance(first.instance, dict):
            missing = [field for field in first.validator_value if field not in first.instance]
        if missing:
            message = f"Schema validation failed at {path}: missing required field(s): {', '.join(missing)}"
            details["missing"] = missing
        else:
            message = f"Schema validation failed at {path}: {first.message}"
    else:
        message = f"Schema validation failed at {path}: {first.message}"
    return [
        AssertionFailure(
            type="json_schema",
            message=message,
            details=details,
        )
    ]
