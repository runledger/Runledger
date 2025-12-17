from __future__ import annotations

from typing import Iterable

from runledger.util.canonical_json import canonical_dumps
from runledger.util.redaction import redact

from .models import CassetteEntry


def find_match(
    entries: Iterable[CassetteEntry], tool_name: str, args: dict[str, object]
) -> CassetteEntry | None:
    target_args = canonical_dumps(redact(args))
    for entry in entries:
        if entry.tool != tool_name:
            continue
        if canonical_dumps(redact(entry.args)) == target_args:
            return entry
    return None


def format_mismatch_error(
    entries: Iterable[CassetteEntry], tool_name: str, args: dict[str, object]
) -> str:
    target_args = canonical_dumps(redact(args))
    available = []
    for entry in entries:
        preview = canonical_dumps(redact(entry.args))
        if len(preview) > 160:
            preview = preview[:157] + "..."
        available.append(f"- {entry.tool} args={preview}")
    if not available:
        available_text = "No cassette entries found."
    else:
        available_text = "\n".join(available)

    return (
        "Cassette mismatch.\n"
        f"Requested tool: {tool_name}\n"
        f"Requested args: {target_args}\n"
        f"Available entries:\n{available_text}"
    )
