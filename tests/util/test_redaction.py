from __future__ import annotations

from runledger.util.redaction import redact, redact_text


def test_redacts_sensitive_keys() -> None:
    payload = {
        "api_key": "secret",
        "nested": {"access_token": "token-value"},
        "tokens_out": 123,
    }
    redacted = redact(payload)

    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["access_token"] == "[REDACTED]"
    assert redacted["tokens_out"] == 123


def test_redacts_bearer_token_in_text() -> None:
    text = "Authorization: Bearer abc.def.ghi"
    assert redact_text(text) == "Authorization: Bearer [REDACTED]"
