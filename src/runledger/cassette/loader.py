from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import CassetteEntry


def _require_mapping(value: Any, *, line_number: int, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Cassette entry must be an object in {path} line {line_number}")
    return value


def load_cassette(path: Path) -> list[CassetteEntry]:
    if not path.is_file():
        raise FileNotFoundError(f"Cassette file not found: {path}")

    entries: list[CassetteEntry] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path} line {line_number}") from exc

        data = _require_mapping(raw, line_number=line_number, path=path)
        tool = data.get("tool")
        args = data.get("args")
        ok = data.get("ok")
        result = data.get("result")
        error = data.get("error")

        if not isinstance(tool, str):
            raise ValueError(f"Cassette entry missing tool in {path} line {line_number}")
        if not isinstance(args, dict):
            raise ValueError(f"Cassette entry missing args in {path} line {line_number}")
        if not isinstance(ok, bool):
            raise ValueError(f"Cassette entry missing ok in {path} line {line_number}")

        entries.append(
            CassetteEntry(
                tool=tool,
                args=args,
                ok=ok,
                result=result,
                error=error if isinstance(error, str) else None,
            )
        )
    return entries
