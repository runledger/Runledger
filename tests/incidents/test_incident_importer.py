from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from runledger.incidents.importer import (
    import_incident,
    normalize_export,
    normalize_run_log,
    read_bundle,
    write_json,
)
from runledger.incidents.replay import evaluate_incident
from runledger.incidents.schema import (
    MAX_BYTES,
    IncidentError,
    canonical,
    parse_json,
    read_bytes,
    validate_incident,
    validate_rules,
)


def source_export() -> dict:
    return {
        "schema_version": 1,
        "incident_id": "private-source-incident-id",
        "title": "private-source-title",
        "metadata": {"deployment": "private-source-metadata"},
        "input": {
            "order_id": "order-private-7042",
            "email": "fabricated.person@example.invalid",
            "request": "private-support-conversation",
            "authorization": "Bearer private-credential-123456",
        },
        "events": [
            {"type": "tool_call", "call_id": "private-source-call-id", "name": "issue_refund",
             "args": {"order_id": "order-private-7042", "amount_cents": 4900}},
            {"type": "business_effect", "call_id": "private-source-call-id",
             "effect": {"type": "refund", "order_id": "order-private-7042",
                        "refund_id": "refund-private-7042", "amount_cents": 4900}},
            {"type": "tool_result", "call_id": "private-source-call-id", "ok": True,
             "result": {"refund_id": "refund-private-7042"}},
            {"type": "final_output", "output": {"status": "refunded", "refund_id": "refund-private-7042"}},
        ],
        "assertions": [
            {"id": "one-refund", "type": "effect_count", "effect_type": "refund",
             "group_by": "order_id", "max": 1},
            {"id": "receipt", "type": "output_equals", "path": "/refund_id", "value": "refund-private-7042"},
        ],
        "effects_complete": True,
    }


def store_source(tmp_path: Path, source: dict | None = None) -> Path:
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source if source is not None else source_export()), encoding="utf-8")
    return path


def refingerprint(bundle: dict) -> None:
    payload = {key: value for key, value in bundle.items() if key != "integrity"}
    bundle["integrity"] = {"sha256": hashlib.sha256(canonical(payload)).hexdigest()}


def test_import_preserves_relations_without_exporting_source_or_lookup_table(tmp_path):
    source = store_source(tmp_path)
    original = source.read_bytes()
    bundle = import_incident(source)
    serialized = json.dumps(bundle)
    for private in ("private-source", "order-private-7042", "refund-private-7042",
                    "fabricated.person", "private-support", "private-credential"):
        assert private not in serialized
    incident = bundle["incident"]
    validate_incident(incident)
    assert incident["input"]["order_id"] == incident["events"][0]["args"]["order_id"]
    assert incident["events"][0]["call_id"] == "c1"
    assert incident["events"][1]["effect"]["refund_id"] == incident["assertions"][1]["value"]
    assert evaluate_incident(incident)["passed"] is True
    assert bundle["redaction"]["raw_source_copied"] is False
    assert bundle["redaction"]["metadata_exported"] is False
    assert source.read_bytes() == original
    assert list(tmp_path.iterdir()) == [source]
    saved = tmp_path / "bundle.json"
    write_json(saved, bundle)
    assert read_bundle(saved) == bundle


def test_imports_are_unlinkable_and_custom_paths_apply(tmp_path):
    raw = source_export()
    raw["input"]["company"] = "private-company-string"
    source = store_source(tmp_path, raw)
    first = import_incident(source, extra_paths=["/input/company"])
    second = import_incident(source, extra_paths=["/input/company"])
    assert "private-company-string" not in json.dumps(first)
    assert first["incident"]["input"]["order_id"] != second["incident"]["input"]["order_id"]
    assert first["incident"]["id"] != second["incident"]["id"]


@pytest.mark.parametrize("raw", [b'{"secret":1,"secret":2}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff'])
def test_invalid_json_has_safe_diagnostic(raw):
    with pytest.raises(IncidentError) as exc:
        parse_json(raw)
    assert "secret" not in str(exc.value)
    assert "NaN" not in str(exc.value)


def test_bounded_read_rejects_oversized_source(tmp_path):
    source = tmp_path / "large.json"
    source.write_bytes(b" " * (MAX_BYTES + 1))
    with pytest.raises(IncidentError, match="4 MiB"):
        read_bytes(source)


@pytest.mark.parametrize("mutation", [
    lambda raw: raw.update(agent_command=["unsafe-command"]),
    lambda raw: raw.update(effects_complete="true"),
    lambda raw: raw["events"][0].update(type=["private-malformed-value"]),
    lambda raw: raw["events"][2].update(call_id="unobserved-call"),
    lambda raw: raw["events"].append({"type": "final_output", "output": {}}),
    lambda raw: raw["events"].pop(),
    lambda raw: raw["events"].insert(1, {"type": "tool_call", "call_id": "second",
                                         "name": "issue_refund", "args": {}}),
])
def test_malformed_canonical_exports_fail_closed(mutation):
    raw = source_export()
    mutation(raw)
    with pytest.raises(IncidentError) as exc:
        normalize_export(raw)
    assert "private-" not in str(exc.value)
    assert "unsafe-command" not in str(exc.value)


def test_malformed_normalized_effect_correlation_has_safe_error():
    normalized = normalize_export(source_export())
    normalized["events"][1]["call_id"] = ["private-malformed-value"]
    with pytest.raises(IncidentError, match="observed call"):
        validate_incident(normalized)


@pytest.mark.parametrize("path", ["status", "/status~", "/status~2", "/status\n"])
def test_invalid_output_json_pointer_is_rejected(path):
    with pytest.raises(IncidentError, match="JSON Pointer"):
        validate_rules([{"id": "status", "type": "output_equals", "path": path, "value": True}])


def test_escaped_json_pointer_targets_exact_output_key():
    raw = source_export()
    raw["events"][-1]["output"] = {"slash/key": {"tilde~key": True}}
    raw["assertions"] = [{"id": "escaped", "type": "output_equals", "path": "/slash~1key/tilde~0key", "value": True}]
    assert evaluate_incident(normalize_export(raw))["passed"] is True


def native_records(case="private-case-id") -> list[dict]:
    return [
        {"case_id": case, "type": "task_start", "input": {"request": "private-native-request"}},
        {"case_id": case, "type": "log", "message": "private-native-log"},
        {"case_id": case, "type": "final_output", "output": {"status": "complete"}},
        {"case_id": case, "type": "assertion_failure", "failures": [{"message": "private-assertion-diagnostic"}]},
        {"case_id": case, "type": "budget_failure", "failures": [{"message": "private-budget-diagnostic"}]},
        {"case_id": case, "type": "case_end", "passed": False, "wall_ms": 123},
    ]


def encode_records(records: list) -> bytes:
    return ("\n".join(json.dumps(record) for record in records) + "\n").encode()


def test_native_failing_engine_log_discards_diagnostics_and_selects_case(tmp_path):
    source = tmp_path / "run.jsonl"
    source.write_bytes(encode_records(native_records() + native_records("other-case")))
    rules = [{"id": "status", "type": "output_equals", "path": "/status", "value": "complete"}]
    bundle = import_incident(source, format="runledger", case="private-case-id", rules=rules)
    assert [event["type"] for event in bundle["incident"]["events"]] == ["final_output"]
    assert "private-" not in json.dumps(bundle)
    assert "other-case" not in json.dumps(bundle)
    assert bundle["incident"]["effects_complete"] is False
    assert evaluate_incident(bundle["incident"])["passed"] is True


def test_native_multi_case_requires_explicit_selection():
    with pytest.raises(IncidentError, match="--case"):
        normalize_run_log(encode_records(native_records("one") + native_records("two")), case=None,
                          rules=[{"id": "errors", "type": "max_tool_errors", "max": 0}])


def test_malformed_native_type_raises_safe_validation_error():
    records = native_records()
    records[1]["type"] = {"private-malformed-value": True}
    with pytest.raises(IncidentError, match="event type must be text"):
        normalize_run_log(encode_records(records), case=None,
                          rules=[{"id": "errors", "type": "max_tool_errors", "max": 0}])


def test_read_bundle_rejects_changed_content(tmp_path):
    bundle = import_incident(store_source(tmp_path))
    bundle["incident"]["events"][-1]["output"]["status"] = "changed"
    saved = tmp_path / "bundle.json"
    write_json(saved, bundle)
    with pytest.raises(IncidentError, match="fingerprint mismatch"):
        read_bundle(saved)


@pytest.mark.parametrize("mutation", [
    lambda bundle: bundle["incident"].update(agent_command=["private-command"]),
    lambda bundle: bundle["boundary"].update(agent="execute bundle commands"),
    lambda bundle: bundle["redaction"].update(review_required=False),
    lambda bundle: bundle.update(schema_version=True),
])
def test_rehashed_bundle_cannot_bypass_schema_or_execution_boundary(tmp_path, mutation):
    bundle = import_incident(store_source(tmp_path))
    mutation(bundle)
    refingerprint(bundle)
    saved = tmp_path / "bundle.json"
    write_json(saved, bundle)
    with pytest.raises(IncidentError) as exc:
        read_bundle(saved)
    assert "private-command" not in str(exc.value)


def test_normalization_does_not_mutate_source():
    raw = source_export()
    before = deepcopy(raw)
    normalize_export(raw)
    assert raw == before
