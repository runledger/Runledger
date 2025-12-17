from __future__ import annotations

from dataclasses import asdict
import hashlib
import time
from pathlib import Path
from typing import Any

from runledger.assertions.engine import apply_assertions, count_assertions
from runledger.cassette.loader import load_cassette
from runledger.cassette.match import find_match, format_mismatch_error
from runledger.cassette.models import CassetteEntry
from runledger.cassette.writer import append_entry
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
from runledger.tools.registry import resolve_tools

from .budgets import check_budgets, merge_budgets
from .models import CaseResult, Failure, SuiteResult


def _event(case_id: str, event_type: str, **fields: Any) -> dict[str, Any]:
    payload = {
        "type": event_type,
        "case_id": case_id,
        "timestamp": time.time(),
    }
    payload.update(fields)
    return payload


def run_case(suite: SuiteConfig, case: CaseConfig) -> CaseResult:
    if suite.mode not in {"replay", "record", "live"}:
        raise ValueError(f"Unsupported mode: {suite.mode}")

    trace: list[dict[str, Any]] = []
    start = time.monotonic()
    tool_calls = 0
    tool_errors = 0
    tool_calls_by_name: dict[str, int] = {}
    tool_errors_by_name: dict[str, int] = {}
    output: dict[str, Any] | None = None
    failure: Failure | None = None
    assertions_total = count_assertions(suite.assertions, case.assertions)
    assertions_failed = 0
    failed_assertions: list[dict[str, str]] | None = None

    cassette_path = Path(case.cassette)
    cassette_entries: list[CassetteEntry] = []
    cassette_sha256: str | None = None
    allowed_tools = set(suite.tool_registry)
    tool_registry = None

    if suite.mode == "replay":
        try:
            cassette_entries = load_cassette(cassette_path)
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
                tool_calls_by_name=tool_calls_by_name,
                tool_errors_by_name=tool_errors_by_name,
                assertions_total=assertions_total,
                assertions_failed=assertions_failed,
                failed_assertions=failed_assertions,
                replay_cassette_path=str(cassette_path),
                replay_cassette_sha256=cassette_sha256,
                failure=failure,
            )
    else:
        try:
            tool_registry = resolve_tools(allowed_tools, suite.tool_module)
        except Exception as exc:
            failure = Failure(type="tool_registry_error", message=str(exc))
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
                tool_calls_by_name=tool_calls_by_name,
                tool_errors_by_name=tool_errors_by_name,
                assertions_total=assertions_total,
                assertions_failed=assertions_failed,
                failed_assertions=failed_assertions,
                replay_cassette_path=str(cassette_path) if suite.mode == "record" else None,
                replay_cassette_sha256=cassette_sha256,
                failure=failure,
            )
        if suite.mode == "record":
            cassette_path.parent.mkdir(parents=True, exist_ok=True)
            cassette_path.write_text("", encoding="utf-8")
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
                    tool_calls += 1
                    tool_calls_by_name[message.name] = tool_calls_by_name.get(message.name, 0) + 1
                    if message.name not in allowed_tools:
                        allowed_list = ", ".join(sorted(allowed_tools)) or "<none>"
                        failure = Failure(
                            type="tool_not_allowed",
                            message=(
                                f"Tool not allowed: {message.name}. "
                                f"Allowed tools: {allowed_list}"
                            ),
                        )
                        break
                    if suite.mode == "replay":
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
                        ok = entry.ok
                        result = entry.result
                        error = entry.error
                    else:
                        assert tool_registry is not None
                        tool = tool_registry.get(message.name)
                        if tool is None:
                            allowed_list = ", ".join(sorted(tool_registry)) or "<none>"
                            failure = Failure(
                                type="tool_not_registered",
                                message=(
                                    f"Tool not registered: {message.name}. "
                                    f"Registered tools: {allowed_list}"
                                ),
                            )
                            break
                        try:
                            result = tool.call(message.args)
                            ok = True
                            error = None
                        except Exception as exc:
                            result = None
                            ok = False
                            error = str(exc)
                        if suite.mode == "record":
                            append_entry(
                                cassette_path,
                                CassetteEntry(
                                    tool=message.name,
                                    args=message.args,
                                    ok=ok,
                                    result=result,
                                    error=error,
                                ),
                            )

                    if not ok:
                        tool_errors += 1
                        tool_errors_by_name[message.name] = (
                            tool_errors_by_name.get(message.name, 0) + 1
                        )
                    tool_result = ToolResultMessage(
                        type="tool_result",
                        call_id=message.call_id,
                        ok=ok,
                        result=result,
                        error=error,
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
            assertions_failed = len(assertion_failures)
            failed_assertions = [
                {"type": failure.type, "message": failure.message}
                for failure in assertion_failures
            ]
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
    effective_budget = merge_budgets(suite.budgets, case.budgets)
    if failure is None and effective_budget is not None:
        budget_failures = check_budgets(
            effective_budget,
            wall_ms=wall_ms,
            tool_calls=tool_calls,
            tool_errors=tool_errors,
        )
        if budget_failures:
            message = "; ".join(
                f"{item['field']} limit={item['limit']} actual={item['actual']}"
                for item in budget_failures
            )
            failure = Failure(type="budget_exceeded", message=f"Budget exceeded: {message}")
            trace.append(
                _event(
                    case.id,
                    "budget_failure",
                    failures=budget_failures,
                )
            )
    passed = failure is None
    trace.append(_event(case.id, "case_end", passed=passed, wall_ms=wall_ms))

    if cassette_path.is_file():
        try:
            cassette_sha256 = hashlib.sha256(cassette_path.read_bytes()).hexdigest()
        except OSError:
            cassette_sha256 = None

    return CaseResult(
        case_id=case.id,
        passed=passed,
        output=output,
        trace=trace,
        wall_ms=wall_ms,
        tool_calls=tool_calls,
        tool_errors=tool_errors,
        tool_calls_by_name=tool_calls_by_name,
        tool_errors_by_name=tool_errors_by_name,
        assertions_total=assertions_total,
        assertions_failed=assertions_failed,
        failed_assertions=failed_assertions,
        replay_cassette_path=str(cassette_path) if suite.mode in {"replay", "record"} else None,
        replay_cassette_sha256=cassette_sha256,
        failure=failure,
    )


def run_suite(suite: SuiteConfig, cases: list[CaseConfig]) -> SuiteResult:
    results = [run_case(suite, case) for case in cases]
    total_cases = len(results)
    passed_cases = sum(1 for result in results if result.passed)
    failed_cases = total_cases - passed_cases
    success_rate = (passed_cases / total_cases) if total_cases else 0.0
    total_tool_calls = sum(result.tool_calls for result in results)
    total_tool_errors = sum(result.tool_errors for result in results)
    total_wall_ms = sum(result.wall_ms for result in results)
    passed = failed_cases == 0

    return SuiteResult(
        suite_name=suite.suite_name,
        cases=results,
        passed=passed,
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        success_rate=success_rate,
        total_tool_calls=total_tool_calls,
        total_tool_errors=total_tool_errors,
        total_wall_ms=total_wall_ms,
    )
