from __future__ import annotations

import os
import sys
from typing import Iterable

from runledger.protocol.messages import ToolCallMessage, ToolResultMessage
from runledger.runner.subprocess import AgentProcess, AgentProcessError


class ToolRegistryError(Exception):
    pass


class ToolProcess:
    """One isolated, stateful tool registry for a single case."""

    def __init__(self, tools: Iterable[str], module: str | None, deadline: float | None):
        self._tools = list(tools)
        self._module = module
        env = dict(os.environ)
        # Preserve runtime import paths, including modules beside the suite and
        # additions made by callers of the Python API.
        env["PYTHONPATH"] = os.pathsep.join(os.path.abspath(path) for path in sys.path)
        self._agent = AgentProcess(
            [sys.executable, "-m", "runledger.runner.tool_worker"],
            timeout_s=None,
            deadline=deadline,
            env=env,
        )

    def __enter__(self) -> "ToolProcess":
        try:
            self._agent.start()
            self._agent.send({
                "type": "task_start", "task_id": "init",
                "input": {"tools": self._tools, "module": self._module},
            })
            response = self._agent.recv()
            if not isinstance(response, ToolResultMessage):
                raise ToolRegistryError("Invalid response from tool worker")
            if not response.ok:
                raise ToolRegistryError(response.error or "Failed to load tool registry")
        except BaseException:
            self._agent.close()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._agent.close()

    def call(self, message: ToolCallMessage) -> ToolResultMessage:
        self._agent.send(message)
        response = self._agent.recv()
        if not isinstance(response, ToolResultMessage) or response.call_id != message.call_id:
            raise AgentProcessError("Invalid response from tool worker", [])
        return response
