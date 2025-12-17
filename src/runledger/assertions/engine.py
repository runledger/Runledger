from __future__ import annotations

from typing import Any, Iterable

from runledger.config.models import AssertionSpec, CaseConfig, SuiteConfig

from .base import AssertionFailure
from .json_schema import apply_json_schema
from .required_fields import apply_required_fields


def _spec_to_dict(spec: AssertionSpec | dict[str, Any]) -> dict[str, Any]:
    if isinstance(spec, dict):
        return dict(spec)
    return spec.model_dump()


def _merge_assertions(
    suite_assertions: Iterable[AssertionSpec],
    case_assertions: Iterable[AssertionSpec] | None,
) -> list[dict[str, Any]]:
    merged = [_spec_to_dict(spec) for spec in suite_assertions]
    if case_assertions:
        merged.extend(_spec_to_dict(spec) for spec in case_assertions)
    return merged


def apply_assertions(
    output: dict[str, Any] | None,
    trace: list[dict[str, Any]],
    suite: SuiteConfig,
    case: CaseConfig,
) -> list[AssertionFailure]:
    _ = trace
    if output is None:
        return [
            AssertionFailure(
                type="no_output",
                message="No final output to apply assertions against",
            )
        ]

    failures: list[AssertionFailure] = []
    for spec in _merge_assertions(suite.assertions, case.assertions):
        assertion_type = spec.get("type")
        if assertion_type == "required_fields":
            fields = spec.get("fields")
            if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
                failures.append(
                    AssertionFailure(
                        type="required_fields",
                        message="required_fields assertion requires a list of field names",
                    )
                )
                continue
            failures.extend(apply_required_fields(output, fields))
        elif assertion_type == "json_schema":
            schema_path = spec.get("schema_path")
            if not isinstance(schema_path, str):
                failures.append(
                    AssertionFailure(
                        type="json_schema",
                        message="json_schema assertion requires schema_path",
                    )
                )
                continue
            failures.extend(apply_json_schema(output, schema_path))
        else:
            failures.append(
                AssertionFailure(
                    type="unknown_assertion",
                    message=f"Unknown assertion type: {assertion_type}",
                )
            )

    return failures
