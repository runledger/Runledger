from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RunInfo(BaseModel):
    run_id: str
    mode: Literal["replay", "record", "live"]
    exit_status: Literal["success", "failed", "error"]
    git_sha: str | None = None
    ci: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class SuiteInfo(BaseModel):
    name: str
    suite_path: str
    agent_command: list[str]
    tool_mode: Literal["replay", "record", "live"]
    suite_config_hash: str | None = None
    cases_total: int | None = None

    model_config = ConfigDict(extra="allow")


class MetricSummary(BaseModel):
    min: float | None = None
    p50: float | None = None
    p95: float | None = None
    mean: float | None = None
    max: float | None = None

    model_config = ConfigDict(extra="allow")


class Aggregates(BaseModel):
    cases_total: int
    cases_pass: int
    cases_fail: int
    cases_error: int
    pass_rate: float
    metrics: dict[str, MetricSummary]

    model_config = ConfigDict(extra="allow")


class AssertionsSummary(BaseModel):
    total: int
    failed: int

    model_config = ConfigDict(extra="allow")


class CaseSummary(BaseModel):
    id: str
    status: Literal["pass", "fail", "error", "skipped"]
    wall_ms: int
    tool_calls: int
    tool_errors: int
    assertions: AssertionsSummary

    model_config = ConfigDict(extra="allow")


class BaselineSummary(BaseModel):
    schema_version: int
    generated_at: str
    runledger_version: str
    run: RunInfo
    suite: SuiteInfo
    aggregates: Aggregates
    cases: list[CaseSummary]

    model_config = ConfigDict(extra="allow")
