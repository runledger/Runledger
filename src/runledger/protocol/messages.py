from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict


class TaskStartMessage(BaseModel):
    type: Literal["task_start"]
    task_id: str
    input: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class ToolResultMessage(BaseModel):
    type: Literal["tool_result"]
    call_id: str
    ok: bool
    result: Any | None = None
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class ToolCallMessage(BaseModel):
    type: Literal["tool_call"]
    name: str
    call_id: str
    args: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class FinalOutputMessage(BaseModel):
    type: Literal["final_output"]
    output: dict[str, Any]

    model_config = ConfigDict(extra="forbid")


class LogMessage(BaseModel):
    type: Literal["log"]
    level: str
    message: str
    data: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class TaskErrorMessage(BaseModel):
    type: Literal["task_error"]
    message: str
    data: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


ProtocolMessage = Union[
    TaskStartMessage,
    ToolResultMessage,
    ToolCallMessage,
    FinalOutputMessage,
    LogMessage,
    TaskErrorMessage,
]

_MESSAGE_TYPES: dict[str, type[BaseModel]] = {
    "task_start": TaskStartMessage,
    "tool_result": ToolResultMessage,
    "tool_call": ToolCallMessage,
    "final_output": FinalOutputMessage,
    "log": LogMessage,
    "task_error": TaskErrorMessage,
}


def parse_message(data: Any) -> ProtocolMessage:
    if not isinstance(data, dict):
        raise ValueError("Protocol message must be a JSON object")
    msg_type = data.get("type")
    if not isinstance(msg_type, str):
        raise ValueError("Protocol message missing type field")
    model = _MESSAGE_TYPES.get(msg_type)
    if model is None:
        raise ValueError(f"Unknown message type: {msg_type}")
    return model.model_validate(data)
