"""Bounded, data-only incident format. Validation errors never echo source data."""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

MAX_BYTES = 4 * 1024 * 1024
MAX_EVENTS = 500
MAX_DEPTH = 20
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,79}")
FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")


class IncidentError(ValueError):
    """A safe diagnostic that does not include imported field values."""


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise IncidentError("Incident contains unsupported JSON values") from exc


def _object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise IncidentError("Duplicate JSON keys are not supported")
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise IncidentError("Non-finite numbers are not supported")


def parse_json(raw: str | bytes) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise IncidentError("Input must contain valid bounded JSON without duplicate keys") from exc


def read_bytes(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise IncidentError("Could not read the input file") from exc
    if len(data) > MAX_BYTES:
        raise IncidentError("Incident exceeds the 4 MiB limit")
    return data


def read_json(path: Path) -> Any:
    return parse_json(read_bytes(path))


def check_tree(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise IncidentError("JSON nesting exceeds the supported limit")
    if isinstance(value, dict):
        if len(value) > 500:
            raise IncidentError("JSON object contains too many fields")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 256 or any(ord(c) < 32 for c in key):
                raise IncidentError("JSON keys must be bounded text without control characters")
            check_tree(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 2000:
            raise IncidentError("JSON array contains too many items")
        for item in value:
            check_tree(item, depth + 1)
    elif isinstance(value, str):
        if len(value) > 65536:
            raise IncidentError("JSON string exceeds the supported length")
    elif value is not None and type(value) not in {int, float, bool}:
        raise IncidentError("Only JSON data is supported")
    elif type(value) is float and not math.isfinite(value):
        raise IncidentError("Non-finite numbers are not supported")


def _fields(value: Any, required: set, optional: set | None = None) -> None:
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - (optional or set()):
        raise IncidentError("Unknown or missing fields in incident data")


def _name(value: Any) -> None:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise IncidentError("Tool, effect, and rule names must be bounded identifiers")


def validate_rules(rules: Any) -> list[dict]:
    if not isinstance(rules, list) or not 1 <= len(rules) <= 30:
        raise IncidentError("Provide between 1 and 30 explicit assertions")
    ids = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise IncidentError("Each assertion must be an object")
        _name(rule.get("id"))
        if rule["id"] in ids:
            raise IncidentError("Assertion IDs must be unique")
        ids.add(rule["id"])
        kind = rule.get("type")
        if kind == "effect_count":
            _fields(rule, {"id", "type", "effect_type", "max"}, {"min", "group_by"})
            _name(rule["effect_type"])
            group = rule.get("group_by")
            if group is not None and (not isinstance(group, str) or not FIELD.fullmatch(group)):
                raise IncidentError("Effect group_by must name a top-level effect field")
            for key in ("min", "max"):
                if key in rule and (type(rule[key]) is not int or not 0 <= rule[key] <= MAX_EVENTS):
                    raise IncidentError("Effect count limits must be bounded nonnegative integers")
            if rule.get("min", 0) > rule["max"]:
                raise IncidentError("Effect count minimum exceeds maximum")
        elif kind == "output_equals":
            _fields(rule, {"id", "type", "path", "value"})
            pointer = rule["path"]
            if (not isinstance(pointer, str) or not pointer.startswith("/") or len(pointer) > 256
                    or re.search(r"~(?![01])", pointer) or any(ord(char) < 32 for char in pointer)):
                raise IncidentError("Output assertion path must be a bounded JSON Pointer")
        elif kind == "required_output":
            _fields(rule, {"id", "type", "fields"})
            if (not isinstance(rule["fields"], list) or not 1 <= len(rule["fields"]) <= 30
                    or not all(isinstance(field, str) and FIELD.fullmatch(field) for field in rule["fields"])):
                raise IncidentError("Required output fields must be bounded identifiers")
        elif kind == "max_tool_errors":
            _fields(rule, {"id", "type", "max"})
            if type(rule["max"]) is not int or not 0 <= rule["max"] <= MAX_EVENTS:
                raise IncidentError("Tool error limit must be a bounded nonnegative integer")
        else:
            raise IncidentError("Unsupported assertion type")
    check_tree(rules)
    return deepcopy(rules)


def validate_incident(value: Any) -> dict:
    """Validate normalized, redacted data; no arbitrary expressions or code."""
    _fields(value, {"id", "input", "events", "assertions", "effects_complete"})
    _name(value["id"])
    if not isinstance(value["input"], dict) or type(value["effects_complete"]) is not bool:
        raise IncidentError("Incident requires an input object and effects_complete boolean")
    check_tree(value)
    validate_rules(value["assertions"])
    events = value["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise IncidentError("Incident requires between 1 and 500 events")
    calls = set()
    pending = None
    terminal = False
    for event in events:
        if not isinstance(event, dict) or terminal:
            raise IncidentError("Invalid event or data after terminal event")
        kind = event.get("type")
        if kind == "tool_call":
            _fields(event, {"type", "call_id", "name", "args"})
            if pending is not None:
                raise IncidentError("Concurrent tool calls are not supported; export a serial incident")
            if not isinstance(event["call_id"], str) or not re.fullmatch(r"c[1-9][0-9]*", event["call_id"]):
                raise IncidentError("Normalized call IDs must use c1, c2, and so on")
            if event["call_id"] in calls or event["call_id"] != f"c{len(calls) + 1}":
                raise IncidentError("Call IDs must be unique and sequential")
            if not isinstance(event["args"], dict):
                raise IncidentError("Tool arguments must be an object")
            _name(event["name"])
            calls.add(event["call_id"])
            pending = event["call_id"]
        elif kind == "tool_result":
            _fields(event, {"type", "call_id", "ok", "result", "error"})
            if pending is None or event["call_id"] != pending or type(event["ok"]) is not bool:
                raise IncidentError("Tool results must match the pending call exactly once")
            if event["error"] is not None and not isinstance(event["error"], str):
                raise IncidentError("Tool result error must be text or null")
            pending = None
        elif kind == "business_effect":
            _fields(event, {"type", "call_id", "effect"})
            if (not isinstance(event["call_id"], str) or event["call_id"] not in calls
                    or not isinstance(event["effect"], dict)):
                raise IncidentError("Business effects must refer to an observed call")
            _name(event["effect"].get("type"))
        elif kind == "final_output":
            _fields(event, {"type", "output"})
            if pending or not isinstance(event["output"], dict):
                raise IncidentError("Final output must be an object after all tool results")
            terminal = True
        elif kind == "task_error":
            _fields(event, {"type", "message"})
            if pending or not isinstance(event["message"], str):
                raise IncidentError("Task error requires text after all tool results")
            terminal = True
        else:
            raise IncidentError("Unsupported incident event type")
    if pending:
        raise IncidentError("Incident has an incomplete tool call; provide its captured response")
    if not terminal:
        raise IncidentError("Incident must end with final_output or task_error")
    if len(canonical(value)) > MAX_BYTES:
        raise IncidentError("Normalized incident exceeds the size limit")
    return deepcopy(value)
