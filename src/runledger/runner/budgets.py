from __future__ import annotations

from typing import Any

from runledger.config.models import BudgetSpec


def merge_budgets(suite_budget: BudgetSpec | None, case_budget: BudgetSpec | None) -> BudgetSpec | None:
    if suite_budget is None and case_budget is None:
        return None

    merged: dict[str, Any] = {}
    if suite_budget is not None:
        merged.update({key: value for key, value in suite_budget.model_dump().items() if value is not None})
    if case_budget is not None:
        merged.update({key: value for key, value in case_budget.model_dump().items() if value is not None})

    return BudgetSpec(**merged)


def check_budgets(
    budget: BudgetSpec,
    *,
    wall_ms: int,
    tool_calls: int,
    tool_errors: int,
) -> list[dict[str, int]]:
    failures: list[dict[str, int]] = []
    if budget.max_wall_ms is not None and wall_ms > budget.max_wall_ms:
        failures.append({"field": "max_wall_ms", "limit": budget.max_wall_ms, "actual": wall_ms})
    if budget.max_tool_calls is not None and tool_calls > budget.max_tool_calls:
        failures.append({"field": "max_tool_calls", "limit": budget.max_tool_calls, "actual": tool_calls})
    if budget.max_tool_errors is not None and tool_errors > budget.max_tool_errors:
        failures.append({"field": "max_tool_errors", "limit": budget.max_tool_errors, "actual": tool_errors})
    return failures
