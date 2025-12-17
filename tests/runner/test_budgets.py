from __future__ import annotations

from runledger.config.models import BudgetSpec
from runledger.runner.budgets import check_budgets, merge_budgets


def test_merge_budgets_prefers_case_over_suite() -> None:
    suite = BudgetSpec(max_wall_ms=100, max_tool_calls=5)
    case = BudgetSpec(max_tool_calls=2)

    merged = merge_budgets(suite, case)
    assert merged is not None
    assert merged.max_wall_ms == 100
    assert merged.max_tool_calls == 2


def test_check_budgets_detects_exceeding_values() -> None:
    budget = BudgetSpec(max_wall_ms=10, max_tool_calls=1, max_tool_errors=0)
    failures = check_budgets(budget, wall_ms=11, tool_calls=2, tool_errors=1)

    fields = {entry["field"] for entry in failures}
    assert fields == {"max_wall_ms", "max_tool_calls", "max_tool_errors"}
