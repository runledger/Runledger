"""Evaluate captured evidence and replay ordered tool responses to a local agent.

This is transcript replay, not a simulated payment provider. Business effects
come from the imported ledger; an unrecorded branch is a divergence, never a
claim that the changed agent is safe. The command is supplied by the caller and
is never taken from an incident bundle.
"""
from __future__ import annotations

import json
import math
import queue
import threading
import time
from copy import deepcopy
from typing import Any

MAX_MESSAGES = 500
MAX_CALLS = 200
MAX_SECONDS = 30.0
MAX_MESSAGE_BYTES = 512 * 1024
_MISSING = object()
_WITHHELD = "Unmatched candidate data withheld; inspect it locally in your own agent."


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def _pointer(value: Any, path: str) -> Any:
    if path == "":
        return value
    if not isinstance(path, str) or not path.startswith("/"):
        return _MISSING
    for raw in path[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            if key not in value:
                return _MISSING
            value = value[key]
        elif isinstance(value, list) and key.isdigit() and (key == "0" or not key.startswith("0")):
            index = int(key)
            if index >= len(value):
                return _MISSING
            value = value[index]
        else:
            return _MISSING
    return value


def evaluate_incident(incident: dict) -> dict:
    """Evaluate declared rules against captured effects and structured output.

    The importer validates the schema first. No code or tool implementation is
    loaded here. Failures are preserved even when the agent never produced a
    final output. Boolean and integer values are distinct when comparing rules.
    """
    events = incident["events"]
    effects = [deepcopy(event["effect"]) for event in events if event["type"] == "business_effect"]
    final = next((event for event in reversed(events) if event["type"] == "final_output"), None)
    task_error = next((event for event in reversed(events) if event["type"] == "task_error"), None)
    output = deepcopy(final["output"]) if final else None
    error = deepcopy(task_error["message"]) if task_error else None
    if output is None and error is None:
        error = "missing_final_output"
    tool_calls = sum(event["type"] == "tool_call" for event in events)
    tool_errors = sum(event["type"] == "tool_result" and not event["ok"] for event in events)
    checks = []
    for rule in incident["assertions"]:
        kind = rule["type"]
        inconclusive = False
        if kind == "effect_count":
            matching = [effect for effect in effects if effect.get("type") == rule["effect_type"]]
            grouped = rule.get("group_by")
            missing_group = False
            counts: dict[str, int] = {}
            if grouped:
                path = grouped if grouped.startswith("/") else "/" + grouped.replace("~", "~0").replace("/", "~1")
                for effect in matching:
                    value = _pointer(effect, path)
                    if value is _MISSING:
                        missing_group = True
                        continue
                    key = _canonical(value)
                    counts[key] = counts.get(key, 0) + 1
            else:
                counts["all"] = len(matching)
            minimum = rule.get("min", 0)
            maximum = rule["max"]
            # Empty group sets do not satisfy a positive minimum.
            passed = not missing_group and (bool(counts) or minimum == 0) and all(
                minimum <= count <= maximum for count in counts.values())
            expected = {"min": minimum, "max": maximum, "per_group": bool(grouped)}
            # Counts are sufficient evidence; group values may be identifying.
            actual = {"total": len(matching), "group_counts": sorted(counts.values()),
                      "missing_group": missing_group}
            detail = (f"Observed {len(matching)} recorded effect(s); "
                      + ("a grouping field is missing." if missing_group
                         else f"allowed count is {minimum} to {maximum}" + (" per group." if grouped else ".")))
            if incident.get("effects_complete") is not True:
                passed = False
                inconclusive = True
                detail = "A complete captured effect ledger is required; missing effects cannot be inferred from tool responses."
        elif kind == "output_equals":
            value = _pointer(output, rule["path"])
            passed = value is not _MISSING and _canonical(value) == _canonical(rule["value"])
            expected = deepcopy(rule["value"])
            actual = {"present": value is not _MISSING,
                      "value": deepcopy(value) if value is not _MISSING else None}
            detail = "Structured output matches the declared value." if passed else "Structured output does not match the declared value."
        elif kind == "required_output":
            missing = [field for field in rule["fields"] if not isinstance(output, dict) or field not in output]
            passed = not missing
            expected = deepcopy(rule["fields"])
            actual = {"missing": missing}
            detail = "All required output fields are present." if passed else "Required output fields are missing."
        elif kind == "max_tool_errors":
            passed = tool_errors <= rule["max"]
            expected = rule["max"]
            actual = tool_errors
            detail = f"Observed {tool_errors} recorded tool error(s); allowed maximum is {rule['max']}."
        else:
            raise ValueError("Unsupported incident assertion type")
        checks.append({"id": rule["id"], "type": kind, "passed": bool(passed),
                       "status": "inconclusive" if inconclusive else "pass" if passed else "fail",
                       "expected": expected, "actual": actual, "detail": detail})
    return {"passed": error is None and output is not None and all(check["passed"] for check in checks),
            "assertions": checks, "effects": effects, "output": output, "error": error,
            "tool_calls": tool_calls, "tool_errors": tool_errors,
            "effects_complete": incident.get("effects_complete") is True}


def _transactions(incident: dict) -> tuple[list[dict], dict | None]:
    calls = []
    current = None
    terminal = None
    for event in incident["events"]:
        kind = event["type"]
        if kind == "tool_call":
            transaction = {"call": event, "events": [], "result": None}
            calls.append(transaction)
            current = transaction
        elif kind in {"business_effect", "tool_result"}:
            if current is None:
                raise ValueError("Recorded tool evidence must follow a tool call")
            # Preserve capture order. A provider audit effect can arrive late,
            # after a later tool result, while still referring to an earlier call.
            current["events"].append(event)
            if kind == "tool_result":
                current["result"] = event
        elif kind in {"final_output", "task_error"}:
            terminal = event
    return calls, terminal


def _bounded_agent_process(command: list[str], timeout_s: float):
    """Add bounded incident readers to the shared process lifecycle.

    Parsing happens behind a bounded queue and bounded readline, not after an
    arbitrary stdout line has already been buffered. Stderr is drained in fixed
    chunks and never retained. Writes also have a deadline: an adapter need not
    read stdin, even when it has emitted a valid tool request.
    """
    from runledger.protocol.messages import parse_message
    from runledger.runner.subprocess import AgentProcess

    from .schema import parse_json

    class BoundedAgentProcess(AgentProcess):
        def __init__(self):
            super().__init__(command, timeout_s=timeout_s, stderr_tail=0,
                             deadline=time.monotonic() + MAX_SECONDS)
            self._stdout_queue = queue.Queue(maxsize=2)
            self._stop = threading.Event()

        def _publish(self, item):
            while not self._stop.is_set():
                try:
                    self._stdout_queue.put(item, timeout=0.05)
                    return
                except queue.Full:
                    continue

        def _read_stdout(self):
            stream = self._require_process().stdout
            try:
                # Count physical lines, including blank lines, to bound floods.
                for _ in range(MAX_MESSAGES):
                    line = stream.readline(MAX_MESSAGE_BYTES + 1)
                    if not line:
                        break
                    if len(line.encode("utf-8")) > MAX_MESSAGE_BYTES:
                        raise ValueError("Agent message exceeds replay limit")
                    if line.strip():
                        self._publish(parse_message(parse_json(line)))
                    if self._stop.is_set():
                        return
                else:
                    raise ValueError("Agent message count exceeds replay limit")
            except Exception:  # noqa: BLE001 - discard all private parser diagnostics
                # Neither a parse exception nor its raw candidate line enters
                # the result, traceback, or retained stderr collection.
                self._publish(ValueError("Invalid or oversized agent protocol message"))
            finally:
                stream.close()
                self._publish(self._stdout_closed)

        def _read_stderr(self):
            stream = self._require_process().stderr
            try:
                while not self._stop.is_set() and stream.read(4096):
                    pass
            except (OSError, UnicodeError):
                pass
            finally:
                stream.close()

        def close(self):
            # Release a reader waiting on the bounded queue before the shared
            # lifecycle kills descendants and joins pipe threads. Launching and
            # sending retain PATH resolution, UTF-8, and deadline handling.
            self._stop.set()
            super().close()

    return BoundedAgentProcess()


def replay_incident(incident: dict, command: list[str], timeout_s: float = 5.0) -> dict:
    """Re-execute a trusted adapter against recorded responses, never live tools.

    Only matching candidate values copied from the redacted incident are retained.
    Unexpected candidate arguments, output, logs, errors, and stderr are withheld
    so a replay cannot accidentally add a fresh credential to a shareable report.
    They still influence matching and assertions in memory.
    """
    if (not isinstance(command, list) or not command
            or not all(isinstance(part, str) and part for part in command)):
        raise ValueError("An explicit nonempty local command argument list is required")
    if (isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float))
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= MAX_SECONDS):
        raise ValueError("Replay timeout must be greater than zero and at most 30 seconds")
    transactions, terminal = _transactions(incident)
    if len(transactions) > MAX_CALLS:
        raise ValueError("Incident exceeds the replay tool-call limit")
    if any(transaction["result"] is None for transaction in transactions):
        raise ValueError("Every recorded tool call needs a recorded result")
    expected = evaluate_incident(incident)
    trace: list[dict] = []
    consumed = 0
    divergence = None
    verdict = "agent_error"
    matched = False
    actual_output = None
    actual_error = None
    output_matches = False
    call_ids: set[str] = set()
    started = time.monotonic()

    def differ(kind: str, reason: str, expected_event: dict | None = None,
               actual_shape: dict | None = None) -> None:
        nonlocal divergence, verdict
        divergence = {"kind": kind, "action_index": consumed + 1, "reason": reason,
                      "expected": deepcopy(expected_event), "actual": actual_shape}
        verdict = "diverged"

    try:
        with _bounded_agent_process(command, float(timeout_s)) as process:
            process.send({"type": "task_start", "task_id": incident["id"], "input": incident["input"]})
            for _ in range(MAX_MESSAGES):
                if time.monotonic() - started >= MAX_SECONDS:
                    actual_error = "replay_time_limit"
                    break
                message = process.recv().model_dump()
                if len(_canonical(message).encode("utf-8")) > MAX_MESSAGE_BYTES:
                    actual_error = "agent_message_too_large"
                    break
                kind = message["type"]
                if kind == "log":
                    # Logs have no role in behavioral reproduction and can carry
                    # fresh secrets even when the imported trace is redacted.
                    continue
                if kind == "tool_call":
                    if consumed >= len(transactions):
                        differ("extra_tool_call", "Agent requested a tool action not present in the recording.",
                               actual_shape={"type": "tool_call", "values_withheld": True})
                        break
                    transaction = transactions[consumed]
                    recorded = transaction["call"]
                    name_matches = message["name"] == recorded["name"]
                    args_match = _canonical(message["args"]) == _canonical(recorded["args"])
                    call_id = message["call_id"]
                    if not call_id or call_id in call_ids:
                        differ("invalid_call_id", "Agent reused an empty or duplicate call ID.", recorded,
                               {"type": "tool_call", "values_withheld": True})
                        break
                    call_ids.add(call_id)
                    if not name_matches or not args_match:
                        differ("tool_call_mismatch", "Agent action diverged from the next recorded tool call.", recorded,
                               {"type": "tool_call", "name_matches": name_matches,
                                "arguments_match": args_match, "values_withheld": True})
                        break
                    trace.append(deepcopy(recorded))
                    # Historical effects are copied only for this consumed call.
                    # They are never synthesized by candidate logs or outputs.
                    trace.extend(deepcopy(transaction["events"]))
                    result = transaction["result"]
                    process.send({"type": "tool_result", "call_id": call_id, "ok": result["ok"],
                                  "result": result.get("result"), "error": result.get("error")})
                    consumed += 1
                    continue
                if kind in {"final_output", "task_error"}:
                    if kind == "final_output":
                        actual_output = message["output"]
                    else:
                        actual_error = message["message"]
                    if consumed != len(transactions):
                        differ("missing_tool_calls", "Agent finished before consuming the recorded tool sequence.",
                               transactions[consumed]["call"], {"type": kind, "values_withheld": True})
                        break
                    same_terminal = terminal is not None and kind == terminal["type"]
                    if same_terminal:
                        same_terminal = (_canonical(message["output"]) == _canonical(terminal["output"])
                                         if kind == "final_output" else message["message"] == terminal["message"])
                    if not same_terminal:
                        differ("terminal_mismatch", "Agent terminal outcome differs from the recording.", terminal,
                               {"type": kind, "values_withheld": True})
                        break
                    trace.append(deepcopy(terminal))
                    matched = True
                    output_matches = True
                    verdict = "reproduced"
                    break
                differ("unexpected_message", "Agent emitted a message type outside the agent protocol.",
                       actual_shape={"values_withheld": True})
                break
            else:
                actual_error = "agent_message_limit"
    except Exception:  # noqa: BLE001 - return safe error codes, never stderr or private exception text
        actual_error = "agent_process_error"

    evaluation_events = deepcopy(trace)
    if not matched:
        if actual_output is not None:
            evaluation_events.append({"type": "final_output", "output": actual_output})
        if actual_error is not None:
            evaluation_events.append({"type": "task_error", "message": "agent_error"})
    observed = evaluate_incident({"events": evaluation_events, "assertions": incident["assertions"],
                                  "effects_complete": incident.get("effects_complete") is True
                                  and consumed == len(transactions)})
    if not matched:
        # A partial transcript is not evidence that a fix passed, even when the
        # subset of historical effects happens to satisfy its numeric rules.
        observed["passed"] = False
        if actual_output is not None and not output_matches:
            observed["output"] = {"withheld": _WITHHELD}
            for check in observed["assertions"]:
                if check["type"] in {"output_equals", "required_output"}:
                    check["actual"] = {"withheld": True}
        if actual_error is not None:
            observed["error"] = "agent_error"
        if divergence is None:
            divergence = {"kind": "agent_error", "action_index": consumed + 1,
                          "reason": "Agent execution stopped before an exact reproduction; error details were withheld.",
                          "expected": None, "actual": {"values_withheld": True}}
        if actual_output is not None:
            trace.append({"type": "final_output", "output": {"withheld": _WITHHELD}})
        if actual_error is not None:
            trace.append({"type": "task_error", "message": "agent_error"})
    return {"matched": matched, "verdict": verdict, "first_divergence": divergence,
            "observed": observed, "expected": expected, "trace": trace,
            "consumed_tool_calls": consumed, "recorded_tool_calls": len(transactions),
            "effects_source": "recorded historical ledger; no live tool executed",
            "execution_boundary": "Explicit local command; external model/network calls are not intercepted."}
