from __future__ import annotations

import json
from pathlib import Path

from runledger.assertions.engine import apply_assertions
from runledger.config.models import AssertionSpec, CaseConfig, SuiteConfig


def _suite_config(assertions: list[AssertionSpec]) -> SuiteConfig:
    return SuiteConfig(
        suite_name="demo",
        agent_command=["python", "agent.py"],
        mode="replay",
        cases_path="cases",
        tool_registry=["search_docs"],
        assertions=assertions,
    )


def _case_config(assertions: list[AssertionSpec] | None = None) -> CaseConfig:
    return CaseConfig(
        id="t1",
        input={},
        cassette="cassettes/t1.jsonl",
        assertions=assertions,
    )


def test_required_fields_missing() -> None:
    suite = _suite_config([AssertionSpec(type="required_fields", fields=["category"])])
    case = _case_config()

    failures = apply_assertions({"reply": "ok"}, [], suite, case)
    assert failures
    assert failures[0].type == "required_fields"


def test_required_fields_merge_with_case_assertions() -> None:
    suite = _suite_config([AssertionSpec(type="required_fields", fields=["category"])])
    case = _case_config([AssertionSpec(type="required_fields", fields=["reply"])])

    failures = apply_assertions({"category": "billing"}, [], suite, case)
    assert failures
    assert any(failure.type == "required_fields" for failure in failures)


def test_json_schema_assertion(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"category": {"type": "string"}},
                "required": ["category"],
            }
        ),
        encoding="utf-8",
    )

    suite = _suite_config([AssertionSpec(type="json_schema", schema_path=str(schema_path))])
    case = _case_config()

    failures = apply_assertions({"reply": "ok"}, [], suite, case)
    assert failures
    assert failures[0].type == "json_schema"
