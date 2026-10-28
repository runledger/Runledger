"""Local, privacy-first redaction for imported production incident data.

The random per-import key and original-to-alias mapping never leave this function.
Aliases preserve equality within one incident, not identity across incidents.
This is a bounded policy, not a claim that arbitrary customer data is anonymous.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
from collections import Counter
from typing import Any

POLICY_VERSION = "incident-redaction-v1"
MAX_DEPTH = 40
MAX_NODES = 100_000
MAX_TEXT = 2 * 1024 * 1024

_PRIORITY = {"freeform": 1, "identifier": 2, "personal": 3, "custom": 4, "secret": 5}
_SECRET_KEYS = {
    "authorization", "proxy_authorization", "cookie", "set_cookie", "password", "passwd",
    "pwd", "passphrase", "secret", "client_secret", "token", "access_token", "refresh_token",
    "id_token", "api_key", "apikey", "x_api_key", "auth", "authentication", "credentials",
    "credential", "session", "session_id", "sessionid", "private_key", "signing_key",
    "card_number", "credit_card", "credit_card_number", "cvv", "cvc", "ssn",
    "social_security_number", "bank_account", "account_number", "routing_number",
}
_PERSONAL_KEYS = {
    "name", "first_name", "last_name", "full_name", "customer_name", "contact_name",
    "display_name", "username", "user_name", "login", "email", "email_address",
    "phone", "telephone", "phone_number", "mobile", "mobile_number", "address",
    "street", "street_address", "billing_address", "shipping_address", "postal_code",
    "zip_code", "zip", "ip", "ip_address", "remote_address", "date_of_birth", "dob",
    "birthdate", "birth_date", "patient", "patient_name", "passport", "national_id",
}
_IDENTIFIER_KEYS = {"id", "idempotency_key", "idempotency", "operation_key", "reference"}
_FREEFORM_KEYS = {
    "message", "messages", "body", "prompt", "reply", "description", "note", "notes",
    "content", "text", "question", "answer", "summary", "title", "subject", "request",
    "instructions", "system_prompt", "user_prompt", "error", "error_message", "stack",
    "stacktrace", "stack_trace", "traceback", "url", "uri", "path", "filename", "file_path",
}
_MACHINE_ERRORS = {
    "provider_timeout", "timeout", "rate_limit", "rate_limited", "refund_declined", "not_found",
    "permission_denied", "authentication_failed", "idempotency_conflict", "invalid_arguments",
    "invalid_request", "service_unavailable", "internal_error", "tool_not_allowed",
    "too_many_requests", "connection_error", "provider_error", "network_error",
}

# Ordered discovery finds both whole credentials and copies embedded in another field.
_PATTERNS = (
    ("secret", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("secret", re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]+)")),
    ("secret", re.compile(r"\bsk-(?:[A-Za-z0-9_-]{12,})\b")),
    ("secret", re.compile(r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9]{20,}\b")),
    ("secret", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("secret", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("secret", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
    ("personal", re.compile(r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}(?![\w.-])")),
    ("personal", re.compile(r"(?<!\w)(?:\+?1[ .-]?)?(?:\([2-9]\d{2}\)|[2-9]\d{2})[ .-]?[2-9]\d{2}[ .-]?\d{4}(?!\w)")),
    ("personal", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("personal", re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")),
    ("personal", re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)),
)


class RedactionError(ValueError):
    """Invalid redaction input; messages never interpolate imported values."""


def _key_kind(key: str) -> str | None:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    parts = set(normalized.split("_"))
    if normalized in _SECRET_KEYS or parts & {"password", "passwd", "secret", "credential", "credentials", "authorization", "cookie", "pwd"} or any(
        normalized.endswith("_" + suffix) for suffix in
        ("password", "secret", "token", "api_key", "cookie", "credentials")
    ):
        return "secret"
    if normalized in _PERSONAL_KEYS or parts & {"email", "phone", "address"} or any(
        normalized.endswith("_" + suffix) for suffix in
        ("email", "phone", "address", "name", "first_name", "last_name", "full_name")
    ):
        return "personal"
    if normalized in _IDENTIFIER_KEYS or normalized.endswith("_id"):
        return "identifier"
    if normalized in _FREEFORM_KEYS:
        return "freeform"
    return None


def _structural(path: tuple[str, ...]) -> bool:
    # Event names are a protocol surface, unlike names inside args/results.
    if len(path) == 3 and path[0] == "events" and path[1].isdigit():
        return path[2] in {"type", "name", "tool", "call_id", "ok", "step", "timestamp"}
    if len(path) == 4 and path[0] == "events" and path[1].isdigit() and path[2] == "effect":
        return path[3] == "type"
    if len(path) == 3 and path[0] == "assertions" and path[1].isdigit():
        return path[2] in {"type", "id", "field", "path", "group_by", "effect_type", "min", "max"}
    if len(path) == 4 and path[0] == "assertions" and path[1].isdigit() and path[2] == "fields":
        return True
    return len(path) == 1 and path[0] in {"schema_version", "kind", "id", "effects_complete"}


def _machine_error(path: tuple[str, ...], value: Any) -> bool:
    return (len(path) == 3 and path[0] == "events" and path[1].isdigit() and path[2] == "error"
            and isinstance(value, str) and value in _MACHINE_ERRORS)


def _pointer(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 512:
        raise RedactionError("Custom redaction paths must be bounded JSON Pointers starting with /")
    parts = value[1:].split("/")
    if any(re.search(r"~(?![01])", part) for part in parts):
        raise RedactionError("Custom redaction path has an invalid JSON Pointer escape")
    return tuple(part.replace("~1", "/").replace("~0", "~") for part in parts)


def _matches(path: tuple[str, ...], pointer: tuple[str, ...]) -> bool:
    return len(path) == len(pointer) and all(p == "*" or p == actual for actual, p in zip(path, pointer))


def redact_incident(
    data: dict,
    *,
    extra_paths: list[str] | None = None,
    keep_paths: list[str] | None = None,
) -> tuple[dict, dict]:
    """Return redacted JSON data plus value-free policy counts and warnings.

    Sensitive objects retain their structure while their scalar values are aliased.
    Numeric IDs/secret values become strings; their repeated numeric/string forms
    receive the same alias. Freeform string fields are replaced wholesale.
    Explicit wildcard JSON Pointers can remove additional domain-specific values.
    No keep-path bypass is supported in this first policy version.
    """
    if not isinstance(data, dict):
        raise RedactionError("Incident redaction requires a JSON object")
    if keep_paths:
        raise RedactionError("Keeping sensitive paths is not supported by this redaction policy")
    if extra_paths is not None and (not isinstance(extra_paths, list) or len(extra_paths) > 100):
        raise RedactionError("Custom redaction paths must be a list of at most 100 JSON Pointers")
    pointers = [_pointer(value) for value in extra_paths or []]
    matches = [0] * len(pointers)
    key = secrets.token_bytes(32)
    values: dict[str, str] = {}
    seen_nodes = 0
    text_bytes = 0

    def forced(path: tuple[str, ...]) -> bool:
        return any(len(path) >= len(pointer) and _matches(path[:len(pointer)], pointer) for pointer in pointers)

    def remember(value: Any, kind: str) -> None:
        if value is None or isinstance(value, bool):
            return
        if isinstance(value, (str, int, float)) and str(value):
            raw = str(value)
            previous = values.get(raw)
            if previous is None or _PRIORITY[kind] > _PRIORITY[previous]:
                values[raw] = kind

    def scan_text(value: str) -> None:
        for kind, pattern in _PATTERNS:
            for match in pattern.finditer(value):
                remember(match.group(), kind)
                # A copied bearer token without its scheme must also disappear.
                if match.lastindex:
                    remember(match.group(1), kind)

    def discover(value: Any, path: tuple[str, ...] = (), inherited: str | None = None) -> None:
        nonlocal seen_nodes, text_bytes
        seen_nodes += 1
        if seen_nodes > MAX_NODES or len(path) > MAX_DEPTH:
            raise RedactionError("Incident exceeds redaction structure limits")
        custom = None
        for index, pointer in enumerate(pointers):
            if _matches(path, pointer):
                if _structural(path):
                    raise RedactionError("Custom paths cannot remove protocol structure")
                matches[index] += 1
                custom = "custom"
        if forced(path) and _structural(path):
            raise RedactionError("Custom paths cannot remove protocol structure")
        structural = _structural(path) or (_machine_error(path, value) and not forced(path))
        kind = custom or inherited
        if path and not structural:
            own_kind = _key_kind(path[-1])
            if own_kind and (kind is None or _PRIORITY[own_kind] > _PRIORITY[kind]):
                kind = own_kind
        if isinstance(value, dict):
            for name, item in value.items():
                if not isinstance(name, str):
                    raise RedactionError("Incident object keys must be strings")
                text_bytes += len(name.encode("utf-8"))
                scan_text(name)
                discover(item, path + (name,), kind)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                discover(item, path + (str(index),), kind)
        elif isinstance(value, str):
            text_bytes += len(value.encode("utf-8"))
            scan_text(value)
            if kind and not structural:
                remember(value, kind)
        elif value is not None and not isinstance(value, (int, float, bool)):
            raise RedactionError("Incident must contain only JSON-compatible values")
        elif isinstance(value, float) and not math.isfinite(value):
            raise RedactionError("Incident must contain finite JSON numbers")
        elif kind in {"secret", "personal", "identifier", "custom", "freeform"} and not structural:
            remember(value, kind)
        if text_bytes > MAX_TEXT:
            raise RedactionError("Incident exceeds redaction text limits")

    try:
        discover(data)
    except (RecursionError, UnicodeError) as exc:
        raise RedactionError("Incident text or nesting is not supported") from exc
    if any(count == 0 for count in matches):
        raise RedactionError("A custom redaction path matched no fields")

    aliases = {
        value: "<redacted:" + kind + ":" + hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:32] + ">"
        for value, kind in values.items()
    }
    # Short values match at token boundaries ("ref: 123"), without treating every
    # "1" in generated call IDs or every "a" in protocol words as the same secret.
    embedded = sorted(values, key=len, reverse=True)
    replacement_pattern = re.compile("|".join(
        re.escape(value) if len(value) >= 4 else r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![A-Za-z0-9])"
        for value in embedded
    )) if embedded else None
    counts: Counter[str] = Counter()
    fields_changed = 0
    numeric_values = 0
    changed_keys = 0

    def replace_text(value: str, *, count: bool = True) -> str:
        if value in aliases:
            if count:
                counts[values[value]] += 1
            return aliases[value]
        if replacement_pattern is None:
            return value
        def substitute(match: re.Match[str]) -> str:
            raw = match.group()
            if count:
                counts[values[raw]] += 1
            return aliases[raw]
        return replacement_pattern.sub(substitute, value)

    def transform(value: Any, path: tuple[str, ...] = ()) -> Any:
        nonlocal fields_changed, numeric_values, changed_keys
        if _structural(path) or (_machine_error(path, value) and not forced(path)):
            if isinstance(value, str) and replace_text(value, count=False) != value:
                raise RedactionError("Sensitive data occurs in protocol structure; normalize it before import")
            return value
        if isinstance(value, dict):
            output = {}
            for name, item in value.items():
                # Fixed root/event keys are defined by the import schema, not data.
                fixed_object = not path or (len(path) == 2 and path[0] in {"events", "assertions"})
                new_name = name if fixed_object else replace_text(name)
                if new_name in output:
                    raise RedactionError("Redaction would collide object keys")
                changed_keys += int(name != new_name)
                output[new_name] = transform(item, path + (name,))
            return output
        if isinstance(value, list):
            return [transform(item, path + (str(index),)) for index, item in enumerate(value)]
        if isinstance(value, str):
            result = replace_text(value)
            fields_changed += int(result != value)
            return result
        if isinstance(value, (int, float)) and not isinstance(value, bool) and str(value) in aliases:
            numeric_values += 1
            fields_changed += 1
            counts[values[str(value)]] += 1
            return aliases[str(value)]
        return value

    redacted = transform(data)
    warnings = [
        "Review the redacted bundle locally before sharing; custom schemas and unrecognized personal data may require additional paths.",
        "Freeform text is removed by default. Redaction can change model decisions and type-sensitive behavior; replay covers the retained tool boundary.",
        "Aliases are consistent only inside this import; the original values and random mapping key are not exported.",
    ]
    if numeric_values:
        warnings.append("Numeric sensitive values were replaced by string aliases; check type-sensitive agent behavior.")
    if changed_keys:
        warnings.append("Sensitive object keys were replaced; check consumers that rely on dynamic keys.")
    if any(len(value) < 4 for value in values):
        warnings.append("Short sensitive values are matched as whole tokens; inspect compound strings and encoded data before sharing.")
    report = {
        "policy_version": POLICY_VERSION,
        "fields_changed": fields_changed,
        "object_keys_changed": changed_keys,
        "numeric_values_replaced": numeric_values,
        "unique_values_replaced": len(values),
        "categories": dict(sorted(counts.items())),
        "custom_paths_applied": len(pointers),
        "warnings": warnings,
    }
    # A final serialization validates the exported shape without logging inputs.
    try:
        json.dumps(redacted, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise RedactionError("Redacted incident could not be serialized") from exc
    return redacted, report
