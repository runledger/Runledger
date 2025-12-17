from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Failure:
    type: str
    message: str


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    passed: bool
    output: dict[str, Any] | None
    trace: list[dict[str, Any]]
    wall_ms: int
    tool_calls: int
    tool_errors: int
    failure: Failure | None = None


@dataclass(frozen=True)
class SuiteResult:
    suite_name: str
    cases: list[CaseResult]
    passed: bool
    total_cases: int
    passed_cases: int
    failed_cases: int
    success_rate: float
    total_tool_calls: int
    total_tool_errors: int
    total_wall_ms: int
