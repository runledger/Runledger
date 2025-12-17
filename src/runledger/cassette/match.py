from __future__ import annotations

from difflib import SequenceMatcher
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
    all_entries = list(entries)
    if not all_entries:
        return (
            "Cassette mismatch.\n"
            f"Requested tool: {tool_name}\n"
            f"Requested args: {target_args}\n"
            "No cassette entries found."
        )

    candidates = [entry for entry in all_entries if entry.tool == tool_name]
    if not candidates:
        candidates = all_entries

    scored = []
    for entry in candidates:
        preview = canonical_dumps(redact(entry.args))
        score = SequenceMatcher(None, target_args, preview).ratio()
        scored.append((score, entry, preview))

    scored.sort(key=lambda item: item[0], reverse=True)
    closest = []
    for score, entry, preview in scored[:5]:
        if len(preview) > 160:
            preview = preview[:157] + "..."
        closest.append(f"- {entry.tool} args={preview} score={score:.2f}")

    available_text = "\n".join(closest)

    return (
        "Cassette mismatch.\n"
        f"Requested tool: {tool_name}\n"
        f"Requested args: {target_args}\n"
        f"Closest matches:\n{available_text}"
    )
