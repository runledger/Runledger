from __future__ import annotations

import json

import pytest

from runledger.incidents.redaction import RedactionError, redact_incident


def incident():
    return {
        "schema_version": 1,
        "incident_id": "production-1234",
        "input": {"order_id": "order-live-1234", "email": "jordan@example.test", "amount_cents": 4900},
        "events": [
            {"type": "tool_call", "call_id": "call-1", "name": "issue_refund", "args": {
                "order_id": "order-live-1234", "idempotency_key": "refund-live-1234", "amount_cents": 4900,
                "headers": {"Authorization": "Bearer bearer-secret-value", "Cookie": "session=private-cookie"},
            }},
            {"type": "tool_result", "call_id": "call-1", "ok": True, "result": {
                "order_id": "order-live-1234", "refund_id": "refund-real-1", "status": "refunded",
                "extra": "jordan@example.test", "copied_token": "bearer-secret-value",
            }},
            {"type": "business_effect", "call_id": "call-1", "effect": {
                "type": "refund", "order_id": "order-live-1234", "amount_cents": 4900,
                "refund_id": "refund-real-1", "approved": True,
            }},
            {"type": "final_output", "output": {"status": "refunded", "refund_id": "refund-real-1",
                                                   "reply": "Dear Jordan, refund for your secret purchase is complete."}},
        ],
        "assertions": [{"id": "one-refund", "type": "max_effects", "effect_type": "refund", "group_by": "order_id", "max": 1}],
    }


def test_redacts_secrets_freeform_and_pii_without_losing_business_values():
    source = incident()
    output, report = redact_incident(source)
    encoded = json.dumps({"output": output, "report": report})
    for value in ("order-live-1234", "jordan@example.test", "refund-live-1234", "bearer-secret-value",
                  "session=private-cookie", "refund-real-1", "secret purchase", "production-1234"):
        assert value not in encoded
    assert output["input"]["amount_cents"] == 4900
    assert output["events"][1]["result"]["status"] == "refunded"
    assert output["events"][2]["effect"]["approved"] is True
    assert output["events"][0]["name"] == "issue_refund"
    assert output["events"][0]["call_id"] == "call-1"
    assert source["input"]["email"] == "jordan@example.test"
    assert report["policy_version"] == "incident-redaction-v1"
    assert report["categories"]["secret"] > 0


def test_aliases_preserve_identity_across_args_results_effects_and_output():
    output, _ = redact_incident(incident())
    order = output["input"]["order_id"]
    assert order == output["events"][0]["args"]["order_id"]
    assert order == output["events"][1]["result"]["order_id"]
    assert order == output["events"][2]["effect"]["order_id"]
    refund = output["events"][1]["result"]["refund_id"]
    assert refund == output["events"][2]["effect"]["refund_id"]
    assert refund == output["events"][3]["output"]["refund_id"]
    assert output["input"]["email"] == output["events"][1]["result"]["extra"]


def test_different_imports_cannot_be_linked_using_deterministic_aliases():
    first, _ = redact_incident(incident())
    second, _ = redact_incident(incident())
    assert first["input"]["order_id"] != second["input"]["order_id"]


def test_distinct_secrets_do_not_collapse_to_one_value():
    output, _ = redact_incident({"input": {"token": "token-one", "password": "token-two"},
                                  "other": ["token-one", "token-two"]})
    assert output["input"]["token"] != output["input"]["password"]
    assert output["other"] == [output["input"]["token"], output["input"]["password"]]


def test_numeric_identifiers_are_consistent_and_explicitly_report_type_change():
    output, report = redact_incident({"input": {"customer_id": 918273}, "other": [918273, "918273"], "amount_cents": 4900})
    alias = output["input"]["customer_id"]
    assert isinstance(alias, str)
    assert output["other"] == [alias, alias]
    assert output["amount_cents"] == 4900
    assert report["numeric_values_replaced"] == 2
    assert any("Numeric" in warning for warning in report["warnings"])


@pytest.mark.parametrize("value", [
    "sk-proj-AbCdEf012345678901234567890123456789", "ghp_" + "a" * 36,
    "github_pat_" + "a" * 40, "AKIA1234567890ABCDEF", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.signature",
    "person@example.com", "+1 (303) 555-0198", "123-45-6789", "192.0.2.45",
    "https://service.example/path?token=private&email=user@example.com",
    "-----BEGIN PRIVATE KEY-----\nprivate material\n-----END PRIVATE KEY-----",
])
def test_patterns_find_sensitive_strings_in_unknown_payload_fields(value):
    output, _ = redact_incident({"input": {"opaque": value, "copy": "prefix " + value + " suffix"}})
    encoded = json.dumps(output)
    assert value not in encoded
    assert "<redacted:" in encoded


def test_custom_wildcard_pointer_and_escaped_keys_apply_to_all_aliases():
    data = {"events": [{"type": "tool_call", "name": "lookup", "call_id": "call-1", "args": {"private/label": "confidential product"}},
                       {"type": "tool_call", "name": "lookup", "call_id": "call-2", "args": {"private/label": "another product"}}],
            "input": {"copied": "confidential product"}}
    output, report = redact_incident(data, extra_paths=["/events/*/args/private~1label"])
    assert output["events"][0]["args"]["private/label"] == output["input"]["copied"]
    assert "confidential product" not in json.dumps(output)
    assert report["custom_paths_applied"] == 1


def test_sensitive_dynamic_keys_are_redacted_and_report_does_not_leak_keys():
    data = {"input": {"name": "Jordan Smith", "lookup": {"Jordan Smith": {"value": 12}, "private@example.test": 33}}}
    output, report = redact_incident(data)
    assert "Jordan Smith" not in json.dumps(output)
    assert "private@example.test" not in json.dumps(output)
    assert report["object_keys_changed"] == 2
    assert "Jordan Smith" not in json.dumps(report)
    assert set(report) == {"policy_version", "fields_changed", "object_keys_changed", "numeric_values_replaced",
                           "unique_values_replaced", "categories", "custom_paths_applied", "warnings"}


@pytest.mark.parametrize("data,kwargs", [
    ({"input": {}}, {"keep_paths": ["/input/secret"]}),
    ({"input": {}}, {"extra_paths": ["/input/missing-private-name"]}),
    ({"input": {}}, {"extra_paths": ["not/a/pointer"]}),
    ({"input": {}}, {"extra_paths": ["/input/~7private"]}),
    ({"events": [{"type": "tool_call", "name": "refund"}]}, {"extra_paths": ["/events/*/name"]}),
    ({"input": {"name": "private-person"}, "events": [{"type": "tool_call", "name": "private-person"}]}, {}),
    ({"input": {"bad": float("nan")}}, {}),
    ({"input": {"bad": object()}}, {}),
])
def test_invalid_inputs_fail_without_echoing_imported_values(data, kwargs):
    with pytest.raises(RedactionError) as error:
        redact_incident(data, **kwargs)
    assert "private-person" not in str(error.value)
    assert "missing-private-name" not in str(error.value)


def test_same_idempotency_key_remains_same_and_changed_retry_key_stays_distinct():
    output, _ = redact_incident({"input": {"idempotency_key": "operation-one"}, "events": [
        {"type": "tool_call", "call_id": "call-1", "name": "refund", "args": {"idempotency_key": "operation-one"}},
        {"type": "tool_call", "call_id": "call-2", "name": "refund", "args": {"idempotency_key": "operation-two"}},
    ]})
    assert output["input"]["idempotency_key"] == output["events"][0]["args"]["idempotency_key"]
    assert output["events"][0]["args"]["idempotency_key"] != output["events"][1]["args"]["idempotency_key"]


def test_bearer_token_copied_without_scheme_is_also_removed():
    output, _ = redact_incident({"input": {"opaque": "Bearer copied-secret", "other": "copied-secret"}})
    assert "copied-secret" not in json.dumps(output)


def test_nested_freeform_scalars_are_removed_including_numeric_values():
    output, _ = redact_incident({"input": {"body": {"content": "medical diagnosis", "amount_cents": 4900},
                                               "messages": [{"role": "user", "content": "private question"}]}})
    assert "medical diagnosis" not in json.dumps(output)
    assert "private question" not in json.dumps(output)
    assert output["input"]["body"]["amount_cents"].startswith("<redacted:freeform:")


def test_boolean_and_null_values_remain_typed():
    output, _ = redact_incident({"input": {"customer_id": None, "secret": False, "approved": True}})
    assert output["input"] == {"customer_id": None, "secret": False, "approved": True}


def test_normalized_schema_survives_redaction_and_retains_machine_errors():
    from runledger.incidents.schema import validate_incident

    data = {
        "id": "incident-aabbccdd", "input": {"customer_id": 1, "order_id": "order-sensitive", "request": "Private request"},
        "effects_complete": True,
        "events": [
            {"type": "tool_call", "call_id": "c1", "name": "issue_refund", "args": {"order_id": "order-sensitive"}},
            {"type": "business_effect", "call_id": "c1", "effect": {"type": "refund", "order_id": "order-sensitive"}},
            {"type": "tool_result", "call_id": "c1", "ok": False, "result": None, "error": "provider_timeout"},
            {"type": "final_output", "output": {"status": "pending", "message": "A private customer message"}},
        ],
        "assertions": [
            {"id": "one-refund", "type": "effect_count", "effect_type": "refund", "group_by": "order_id", "max": 1},
            {"id": "message-match", "type": "output_equals", "path": "/message", "value": "A private customer message"},
            {"id": "required", "type": "required_output", "fields": ["status", "message"]},
        ],
    }
    validate_incident(data)
    output, _ = redact_incident(data)
    assert validate_incident(output) == output
    assert output["id"] == "incident-aabbccdd"
    assert output["assertions"][0]["max"] == 1
    assert output["events"][2]["error"] == "provider_timeout"
    assert output["events"][3]["output"]["message"] == output["assertions"][1]["value"]
    assert output["assertions"][1]["path"] == "/message"


def test_unknown_error_text_is_removed_even_if_it_looks_like_a_machine_code():
    output, _ = redact_incident({"events": [{"type": "tool_result", "call_id": "c1", "error": "customer_jordan_secret"}]})
    assert output["events"][0]["error"].startswith("<redacted:freeform:")


def test_custom_pointer_can_remove_an_allowed_machine_error_explicitly():
    output, _ = redact_incident({"events": [{"type": "tool_result", "call_id": "c1", "error": "provider_timeout"}]},
                                 extra_paths=["/events/*/error"])
    assert "provider_timeout" not in json.dumps(output)


def test_short_identifiers_and_secrets_are_redacted_in_copied_tokens():
    output, report = redact_incident({"input": {"customer_id": 123, "password": "xy"},
                                      "other": ["ref: 123", "credential='xy'", "number1234"]})
    assert output["other"][0] == "ref: " + output["input"]["customer_id"]
    assert output["other"][1] == "credential='" + output["input"]["password"] + "'"
    assert output["other"][2] == "number1234"
    assert any("Short sensitive values" in warning for warning in report["warnings"])


@pytest.mark.parametrize("key", ["passwordHash", "clientSecretValue", "credentials_b64", "recipientName", "shippingAddressLine1"])
def test_sensitive_key_variants_do_not_require_exact_spellings(key):
    output, _ = redact_incident({"input": {key: "opaque-private-value"}})
    assert "opaque-private-value" not in json.dumps(output)
