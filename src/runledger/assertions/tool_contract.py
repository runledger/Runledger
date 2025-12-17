from __future__ import annotations

from typing import Iterable

from .base import AssertionFailure


def _tool_calls(trace: list[dict[str, object]]) -> list[str]:
    calls: list[str] = []
    for event in trace:
        if event.get("type") != "tool_call":
            continue
        name = event.get("name")
        if isinstance(name, str):
            calls.append(name)
    return calls


def apply_must_call(trace: list[dict[str, object]], tools: list[str]) -> list[AssertionFailure]:
    calls = _tool_calls(trace)
    missing = [tool for tool in tools if tool not in calls]
    if not missing:
        return []
    return [
        AssertionFailure(
            type="must_call",
            message=(
                f"Missing required tool calls: {', '.join(missing)}. "
                f"Observed: {', '.join(calls) if calls else '<none>'}"
            ),
            details={"missing": missing, "observed_calls": calls},
        )
    ]


def apply_must_not_call(trace: list[dict[str, object]], tools: list[str]) -> list[AssertionFailure]:
    calls = _tool_calls(trace)
    forbidden = [tool for tool in tools if tool in calls]
    if not forbidden:
        return []
    return [
        AssertionFailure(
            type="must_not_call",
            message=(
                f"Forbidden tool calls observed: {', '.join(forbidden)}. "
                f"Observed: {', '.join(calls) if calls else '<none>'}"
            ),
            details={"forbidden": forbidden, "observed_calls": calls},
        )
    ]


def apply_call_order(trace: list[dict[str, object]], order: list[str]) -> list[AssertionFailure]:
    if not order:
        return []
    calls = _tool_calls(trace)
    idx = 0
    for call in calls:
        if call == order[idx]:
            idx += 1
            if idx == len(order):
                return []
    return [
        AssertionFailure(
            type="call_order",
            message=f"Tool call order not satisfied: {' -> '.join(order)}",
            details={"expected_order": order, "observed_calls": calls},
        )
    ]
