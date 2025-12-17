from __future__ import annotations

from dataclasses import dataclass, field
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
    tool_calls_by_name: dict[str, int] = field(default_factory=dict)
    tool_errors_by_name: dict[str, int] = field(default_factory=dict)
    assertions_total: int = 0
    assertions_failed: int = 0
    failed_assertions: list[dict[str, str]] | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    steps: int | None = None
    replay_cassette_path: str | None = None
    replay_cassette_sha256: str | None = None
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
