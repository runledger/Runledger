from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AssertionSpec(BaseModel):
    type: str

    model_config = ConfigDict(extra="allow")


class BudgetSpec(BaseModel):
    max_wall_ms: int | None = None
    max_tool_calls: int | None = None
    max_tool_errors: int | None = None
    max_tokens_out: int | None = None
    max_cost_usd: float | None = None

    model_config = ConfigDict(extra="forbid")


class RegressionSpec(BaseModel):
    min_pass_rate: float | None = Field(
        default=None,
        validation_alias=AliasChoices("min_pass_rate", "min_success_rate"),
    )
    max_avg_wall_ms_delta_pct: float | None = Field(
        default=None,
        validation_alias=AliasChoices("max_avg_wall_ms_delta_pct"),
    )
    max_p95_wall_ms_delta_pct: float | None = Field(
        default=None,
        validation_alias=AliasChoices("max_p95_wall_ms_delta_pct", "max_p95_wall_ms_increase_pct"),
    )

    model_config = ConfigDict(extra="allow")


class SuiteConfig(BaseModel):
    suite_name: str
    agent_command: list[str]
    mode: Literal["replay", "record", "live"]
    cases_path: str
    tool_registry: list[str]
    tool_module: str | None = None
    assertions: list[AssertionSpec] = Field(default_factory=list)
    budgets: BudgetSpec | None = None
    regression: RegressionSpec | None = None
    baseline_path: str | None = None
    output_dir: str | None = None

    model_config = ConfigDict(extra="forbid")


class CaseConfig(BaseModel):
    id: str
    description: str | None = None
    input: dict[str, object]
    cassette: str
    assertions: list[AssertionSpec] | None = None
    budgets: BudgetSpec | None = None

    model_config = ConfigDict(extra="forbid")
