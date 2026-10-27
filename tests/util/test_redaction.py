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


def test_redacts_common_secret_patterns() -> None:
    openai_key = "sk-" + ("a" * 24)
    github_token = "ghp_" + ("b" * 36)
    aws_key = "AKIA" + ("C" * 16)
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )
    text = f"keys {openai_key} {github_token} {aws_key} {jwt} end"
    redacted = redact_text(text)
    assert openai_key not in redacted
    assert github_token not in redacted
    assert aws_key not in redacted
    assert jwt not in redacted
    assert redacted.count("[REDACTED]") == 4
