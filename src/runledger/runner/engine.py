from __future__ import annotations

from dataclasses import asdict
import time
from pathlib import Path
from typing import Any

from runledger.assertions.engine import apply_assertions
from runledger.cassette.loader import load_cassette
from runledger.cassette.match import find_match, format_mismatch_error
from runledger.config.models import CaseConfig, SuiteConfig
from runledger.protocol.messages import (
    FinalOutputMessage,
    LogMessage,
    TaskErrorMessage,
    TaskStartMessage,
    ToolCallMessage,
    ToolResultMessage,
)
from runledger.runner.subprocess import AgentProcess, AgentProcessError

from .models import CaseResult, Failure


def _event(case_id: str, event_type: str, **fields: Any) -> dict[str, Any]:
    payload = {
        "type": event_type,
        "case_id": case_id,
        "timestamp": time.time(),
    }
    payload.update(fields)
    return payload


def run_case(suite: SuiteConfig, case: CaseConfig) -> CaseResult:
    if suite.mode != "replay":
        raise ValueError("Only replay mode supported in MVP")

    trace: list[dict[str, Any]] = []
    start = time.monotonic()
    tool_calls = 0
    tool_errors = 0
    output: dict[str, Any] | None = None
    failure: Failure | None = None

    try:
        cassette_entries = load_cassette(Path(case.cassette))
    except Exception as exc:
        failure = Failure(type="cassette_error", message=str(exc))
        wall_ms = int((time.monotonic() - start) * 1000)
        trace.append(_event(case.id, "case_end", passed=False, wall_ms=wall_ms))
        return CaseResult(
            case_id=case.id,
            passed=False,
            output=None,
            trace=trace,
            wall_ms=wall_ms,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
            failure=failure,
        )

    allowed_tools = set(suite.tool_registry)
    task_start = TaskStartMessage(type="task_start", task_id=case.id, input=case.input)
    trace.append(_event(case.id, "task_start", task_id=case.id, input=case.input))

    try:
        with AgentProcess(suite.agent_command) as agent:
            agent.send(task_start)
            while True:
                message = agent.recv()

                if isinstance(message, ToolCallMessage):
                    trace.append(
                        _event(
                            case.id,
                            "tool_call",
                            name=message.name,
                            call_id=message.call_id,
                            args=message.args,
                        )
                    )
                    if message.name not in allowed_tools:
                        failure = Failure(
                            type="tool_not_allowed",
                            message=f"Tool not allowed: {message.name}",
                        )
                        break
                    entry = find_match(cassette_entries, message.name, message.args)
                    if entry is None:
                        failure = Failure(
                            type="cassette_mismatch",
                            message=format_mismatch_error(
                                cassette_entries,
                                message.name,
                                message.args,
                            ),
                        )
                        break
                    tool_calls += 1
                    if not entry.ok:
                        tool_errors += 1
                    tool_result = ToolResultMessage(
                        type="tool_result",
                        call_id=message.call_id,
                        ok=entry.ok,
                        result=entry.result,
                        error=entry.error,
                    )
                    agent.send(tool_result)
                    trace.append(
                        _event(
                            case.id,
                            "tool_result",
                            call_id=tool_result.call_id,
                            ok=tool_result.ok,
                            result=tool_result.result,
                            error=tool_result.error,
                        )
                    )
                    continue

                if isinstance(message, FinalOutputMessage):
                    output = message.output
                    trace.append(_event(case.id, "final_output", output=output))
                    break

                if isinstance(message, LogMessage):
                    trace.append(
                        _event(
                            case.id,
                            "log",
                            level=message.level,
                            message=message.message,
                            data=message.data,
                        )
                    )
                    continue

                if isinstance(message, TaskErrorMessage):
                    trace.append(
                        _event(
                            case.id,
                            "task_error",
                            message=message.message,
                            data=message.data,
                        )
                    )
                    failure = Failure(type="task_error", message=message.message)
                    break
    except AgentProcessError as exc:
        failure = Failure(type="agent_error", message=str(exc))

    if failure is None and output is not None:
        assertion_failures = apply_assertions(output, trace, suite, case)
        if assertion_failures:
            failure = Failure(
                type="assertion_failed",
                message="\n".join(f.message for f in assertion_failures),
            )
            trace.append(
                _event(
                    case.id,
                    "assertion_failure",
                    failures=[asdict(failure) for failure in assertion_failures],
                )
            )

    wall_ms = int((time.monotonic() - start) * 1000)
    passed = failure is None
    trace.append(_event(case.id, "case_end", passed=passed, wall_ms=wall_ms))

    return CaseResult(
        case_id=case.id,
        passed=passed,
        output=output,
        trace=trace,
        wall_ms=wall_ms,
        tool_calls=tool_calls,
        tool_errors=tool_errors,
        failure=failure,
    )
