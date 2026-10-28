"""Normalize and redact local exported incidents; never read remote resources."""
from __future__ import annotations

import hashlib
import json
import secrets
from copy import deepcopy
from pathlib import Path

from .redaction import redact_incident
from .schema import (
    IncidentError,
    _fields,
    canonical,
    check_tree,
    parse_json,
    read_bytes,
    read_json,
    validate_incident,
    validate_rules,
)

BOUNDARY = {
    "tools": "ordered recorded responses; no tool implementation is executed",
    "effects": "historical evidence supplied by the exporter; not recreated provider state",
    "agent": "explicit trusted local command only; not sandboxed",
    "models": "calls outside the JSONL tool boundary are not frozen or intercepted",
    "redaction": "review required; content transformations can change agent behavior",
}


def _normalize_events(raw_events: list) -> list[dict]:
    if not isinstance(raw_events, list) or len(raw_events) > 500:
        raise IncidentError("Incident requires at most 500 events")
    mapping = {}
    events = []
    for event in raw_events:
        if not isinstance(event, dict):
            raise IncidentError("Each incident event must be an object")
        kind = event.get("type")
        if not isinstance(kind, str):
            raise IncidentError("Incident event type must be text")
        if kind == "tool_call":
            _fields(event, {"type", "call_id", "name", "args"}, {"timestamp"})
            original = event["call_id"]
            if not isinstance(original, str) or not original or len(original) > 256 or original in mapping:
                raise IncidentError("Source tool call IDs must be unique bounded strings")
            mapping[original] = f"c{len(mapping) + 1}"
            events.append({"type": kind, "call_id": mapping[original], "name": event["name"], "args": event["args"]})
        elif kind in {"tool_result", "business_effect"}:
            required = {"type", "call_id", "ok"} if kind == "tool_result" else {"type", "call_id", "effect"}
            optional = {"timestamp", "result", "error"} if kind == "tool_result" else {"timestamp"}
            _fields(event, required, optional)
            original = event["call_id"]
            if not isinstance(original, str) or original not in mapping:
                raise IncidentError("Result/effect has no preceding matching call")
            normalized = {"type": kind, "call_id": mapping[original]}
            if kind == "tool_result":
                normalized.update(ok=event["ok"], result=event.get("result"), error=event.get("error"))
            else:
                normalized["effect"] = event["effect"]
            events.append(normalized)
        elif kind == "final_output":
            _fields(event, {"type", "output"}, {"timestamp"})
            events.append({"type": kind, "output": event["output"]})
        elif kind == "task_error":
            _fields(event, {"type", "message"}, {"timestamp", "data"})
            events.append({"type": kind, "message": event["message"]})
        else:
            raise IncidentError("Unsupported canonical event; export only calls, results, effects, and terminal outcome")
    return events


def normalize_export(raw: dict, rules: list | None = None) -> dict:
    _fields(raw, {"schema_version", "input", "events"},
            {"incident_id", "title", "metadata", "source", "assertions", "effects_complete"})
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise IncidentError("Unsupported incident export version")
    check_tree(raw)
    normalized = {"id": "incident-" + secrets.token_hex(8), "input": deepcopy(raw["input"]),
                  "events": _normalize_events(deepcopy(raw["events"])),
                  "assertions": validate_rules(rules if rules is not None else raw.get("assertions")),
                  "effects_complete": raw.get("effects_complete", False)}
    return validate_incident(normalized)


def normalize_run_log(raw: bytes, *, case: str | None, rules: list, effects_complete: bool = False) -> dict:
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeError as exc:
        raise IncidentError("Run log must be UTF-8 JSONL") from exc
    if len(lines) > 4000:
        raise IncidentError("Run log contains too many lines; export one bounded incident")
    records = [parse_json(line) for line in lines if line.strip()]
    if not records or not all(isinstance(item, dict) for item in records):
        raise IncidentError("Run log must contain JSON objects")
    cases = {item.get("case_id") for item in records if isinstance(item.get("case_id"), str)}
    if case is None:
        if len(cases) != 1:
            raise IncidentError("Select exactly one case with --case")
        case = next(iter(cases))
    selected = [item for item in records if item.get("case_id") == case]
    starts = [item for item in selected if item.get("type") == "task_start"]
    if len(starts) != 1:
        raise IncidentError("Selected case requires exactly one task_start")
    allowed = {"tool_call": {"type", "call_id", "name", "args"},
               "tool_result": {"type", "call_id", "ok", "result", "error"},
               "business_effect": {"type", "call_id", "effect"},
               "final_output": {"type", "output"}, "task_error": {"type", "message"}}
    events = []
    for record in selected:
        kind = record.get("type")
        if not isinstance(kind, str):
            raise IncidentError("Run log event type must be text")
        if kind in allowed:
            events.append({key: value for key, value in record.items() if key in allowed[kind]})
        elif kind not in {"task_start", "case_end", "log", "assertion", "assertion_failure", "budget_failure"}:
            raise IncidentError("Run log contains unsupported event types")
    return normalize_export({"schema_version": 1, "input": starts[0].get("input"),
                             "events": events, "assertions": rules, "effects_complete": effects_complete})


def seal(incident: dict, redaction: dict) -> dict:
    incident = validate_incident(incident)
    payload = {"schema_version": 1, "kind": "runledger.production-incident",
               "incident": incident, "redaction": redaction, "boundary": dict(BOUNDARY)}
    return {**payload, "integrity": {"sha256": hashlib.sha256(canonical(payload)).hexdigest()}}


def import_incident(path: Path, *, format: str = "canonical", case: str | None = None,
                    rules: list | None = None, extra_paths: list[str] | None = None,
                    effects_complete: bool = False) -> dict:
    if format == "canonical":
        normalized = normalize_export(read_json(path), rules)
    elif format == "runledger":
        normalized = normalize_run_log(read_bytes(path), case=case,
                                       rules=validate_rules(rules), effects_complete=effects_complete)
    else:
        raise IncidentError("Unsupported import format")
    sanitized, report = redact_incident(normalized, extra_paths=extra_paths)
    # Fields outside the normalized schema are discarded before redaction.
    report = {**report, "metadata_exported": False, "review_required": True,
              "source_format": format, "raw_source_copied": False,
              "note": "No originals, lookup table, or redaction key are saved. Review before sharing."}
    return seal(sanitized, report)


def read_bundle(path: Path) -> dict:
    bundle = read_json(path)
    _fields(bundle, {"schema_version", "kind", "incident", "redaction", "boundary", "integrity"})
    if type(bundle["schema_version"]) is not int or bundle["schema_version"] != 1:
        raise IncidentError("Unsupported incident bundle version")
    if bundle["kind"] != "runledger.production-incident" or bundle["boundary"] != BOUNDARY:
        raise IncidentError("Unsupported incident bundle kind or execution boundary")
    _fields(bundle["integrity"], {"sha256"})
    digest = bundle["integrity"]["sha256"]
    if not isinstance(digest, str) or not re_full_hash(digest):
        raise IncidentError("Invalid incident fingerprint")
    payload = {key: value for key, value in bundle.items() if key != "integrity"}
    if hashlib.sha256(canonical(payload)).hexdigest() != digest:
        raise IncidentError("Incident fingerprint mismatch; contents changed")
    validate_incident(bundle["incident"])
    if not isinstance(bundle["redaction"], dict) or bundle["redaction"].get("review_required") is not True:
        raise IncidentError("Incident bundle requires its redaction review notice")
    check_tree(bundle)
    return bundle


def re_full_hash(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")
