from __future__ import annotations

from typing import Any

from .base import AssertionFailure


def apply_required_fields(output: dict[str, Any], fields: list[str]) -> list[AssertionFailure]:
    missing = [field for field in fields if field not in output]
    if not missing:
        return []
    message = f"Missing required fields: {', '.join(missing)}"
    return [
        AssertionFailure(
            type="required_fields",
            message=message,
            details={"missing": missing},
        )
    ]
