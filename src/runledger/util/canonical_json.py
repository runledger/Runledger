from __future__ import annotations

import json
from typing import Any


def canonicalize_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: canonicalize_json(obj[key]) for key in sorted(obj)}
    if isinstance(obj, list):
        return [canonicalize_json(item) for item in obj]
    return obj


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        canonicalize_json(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
