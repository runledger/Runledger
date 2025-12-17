from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol


class Tool(Protocol):
    name: str

    def call(self, args: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class FunctionTool:
    name: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]

    def call(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.handler(args)


def _coerce_tool(name: str, value: object) -> Tool:
    if isinstance(value, FunctionTool):
        return value
    if callable(value):
        return FunctionTool(name=name, handler=value)
    if hasattr(value, "call"):
        tool = value
        if getattr(tool, "name", None) is None:
            setattr(tool, "name", name)
        return tool  # type: ignore[return-value]
    raise TypeError(f"Tool {name!r} is not callable or Tool-like")


def load_tool_module(module_path: str) -> dict[str, Tool]:
    module = importlib.import_module(module_path)
    if not hasattr(module, "TOOLS"):
        raise ValueError(f"Tool module {module_path!r} must define TOOLS")
    raw_tools = getattr(module, "TOOLS")
    if not isinstance(raw_tools, dict):
        raise TypeError(f"TOOLS in {module_path!r} must be a dict of name -> tool")
    tools: dict[str, Tool] = {}
    for name, value in raw_tools.items():
        tools[name] = _coerce_tool(name, value)
    return tools


def resolve_tools(allowed: Iterable[str], module_path: str | None) -> dict[str, Tool]:
    tools = load_tool_module("runledger.tools.builtin")
    if module_path:
        tools.update(load_tool_module(module_path))
    allowed_list = list(allowed)
    missing = [name for name in allowed_list if name not in tools]
    if missing:
        raise ValueError(f"Tools not found in registry: {', '.join(sorted(missing))}")
    return {name: tools[name] for name in allowed_list}
