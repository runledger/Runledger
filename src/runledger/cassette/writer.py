from __future__ import annotations

import json
from pathlib import Path

from .models import CassetteEntry
from runledger.util.redaction import redact


def append_entry(path: Path, entry: CassetteEntry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool": entry.tool,
        "args": entry.args,
        "ok": entry.ok,
        "result": entry.result,
    }
    if entry.error is not None:
        payload["error"] = entry.error
    payload = redact(payload)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
