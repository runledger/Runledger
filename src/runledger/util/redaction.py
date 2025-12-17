from __future__ import annotations

import re
from typing import Any

_SENSITIVE_SUBSTRINGS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "auth_token",
)
_SENSITIVE_PARTS = {
    "token",
    "secret",
    "password",
    "pwd",
    "auth",
}

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\\bsk-[A-Za-z0-9]{20,}\\b"), "[REDACTED]"),
    (re.compile(r"\\bghp_[A-Za-z0-9]{36}\\b"), "[REDACTED]"),
    (re.compile(r"\\bAKIA[0-9A-Z]{16}\\b"), "[REDACTED]"),
    (
        re.compile(r"\\beyJ[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+\\b"),
        "[REDACTED]",
    ),
]


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    for substring in _SENSITIVE_SUBSTRINGS:
        if substring in key_lower:
            return True
    parts = [part for part in re.split(r"[^a-z0-9]+", key_lower) if part]
    return any(part in _SENSITIVE_PARTS for part in parts)


def redact_text(text: str) -> str:
    redacted = text
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _is_sensitive_key(key):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
