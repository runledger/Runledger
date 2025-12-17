from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class SuiteConfig(BaseModel):
    suite_name: str
    agent_command: list[str]
    mode: Literal["replay", "record", "live"]
    cases_path: str
    tool_registry: list[str]
    assertions: list[AssertionSpec] = Field(default_factory=list)
    budgets: BudgetSpec | None = None
    baseline_path: str | None = None
    output_dir: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_mode(self) -> "SuiteConfig":
        if self.mode != "replay":
            raise ValueError("Only replay mode supported in MVP")
        return self


class CaseConfig(BaseModel):
    id: str
    description: str | None = None
    input: dict[str, object]
    cassette: str
    assertions: list[AssertionSpec] | None = None
    budgets: BudgetSpec | None = None

    model_config = ConfigDict(extra="forbid")
