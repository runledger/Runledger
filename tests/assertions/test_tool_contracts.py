from __future__ import annotations

from runledger.assertions.engine import apply_assertions
from runledger.config.models import AssertionSpec, CaseConfig, SuiteConfig


def _suite(assertions: list[AssertionSpec]) -> SuiteConfig:
    return SuiteConfig(
        suite_name="demo",
        agent_command=["python", "agent.py"],
        mode="replay",
        cases_path="cases",
        tool_registry=["search_docs", "create_issue"],
        assertions=assertions,
    )


def _case() -> CaseConfig:
    return CaseConfig(
        id="t1",
        input={},
        cassette="cassettes/t1.jsonl",
    )


def _trace(*tools: str) -> list[dict[str, object]]:
    return [
        {"type": "tool_call", "name": tool, "call_id": f"c{idx}", "args": {}}
        for idx, tool in enumerate(tools, start=1)
    ]


def test_must_call_detects_missing_tools() -> None:
    suite = _suite([AssertionSpec(type="must_call", tools=["search_docs", "create_issue"])])
    case = _case()

    failures = apply_assertions({"ok": True}, _trace("search_docs"), suite, case)
    assert failures
    assert failures[0].type == "must_call"


def test_must_not_call_detects_forbidden_tools() -> None:
    suite = _suite([AssertionSpec(type="must_not_call", tools=["create_issue"])])
    case = _case()

    failures = apply_assertions({"ok": True}, _trace("create_issue"), suite, case)
    assert failures
    assert failures[0].type == "must_not_call"


def test_call_order_passes_when_in_order() -> None:
    suite = _suite([AssertionSpec(type="call_order", order=["search_docs", "create_issue"])])
    case = _case()

    failures = apply_assertions({"ok": True}, _trace("search_docs", "create_issue"), suite, case)
    assert failures == []


def test_call_order_fails_when_out_of_order() -> None:
    suite = _suite([AssertionSpec(type="call_order", order=["search_docs", "create_issue"])])
    case = _case()

    failures = apply_assertions({"ok": True}, _trace("create_issue", "search_docs"), suite, case)
    assert failures
    assert failures[0].type == "call_order"
