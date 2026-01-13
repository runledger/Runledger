from __future__ import annotations

from runledger.config.models import NormalizationSpec, ReplaceTextSpec
from runledger.util.normalize import normalize


def test_strip_keys_recursive() -> None:
    spec = NormalizationSpec(strip_keys=["timestamp", "id"])
    payload = {
        "id": "root",
        "name": "demo",
        "meta": {"timestamp": "2025-01-01T00:00:00Z", "keep": True},
        "items": [{"id": "a"}, {"id": "b", "keep": 1}],
    }

    normalized = normalize(payload, spec)

    assert normalized == {
        "name": "demo",
        "meta": {"keep": True},
        "items": [{}, {"keep": 1}],
    }


def test_strip_paths_and_replace_paths() -> None:
    spec = NormalizationSpec(
        strip_paths=["meta.seed", "items.*.rand"],
        replace_paths={"meta.request_id": "<id>"},
    )
    payload = {
        "meta": {"seed": 42, "request_id": "abc-123"},
        "items": [{"rand": 1, "value": 10}, {"rand": 2, "value": 20}],
    }

    normalized = normalize(payload, spec)

    assert normalized == {
        "meta": {"request_id": "<id>"},
        "items": [{"value": 10}, {"value": 20}],
    }


def test_replace_text() -> None:
    spec = NormalizationSpec(
        replace_text=[ReplaceTextSpec(pattern=r"\\d{4}-\\d{2}-\\d{2}", replacement="<date>")]
    )
    payload = {"message": "created on 2025-01-30", "nested": ["2024-12-01 ok"]}

    normalized = normalize(payload, spec)

    assert normalized == {"message": "created on <date>", "nested": ["<date> ok"]}
