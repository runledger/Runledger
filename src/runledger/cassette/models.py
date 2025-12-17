from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CassetteEntry:
    tool: str
    args: dict[str, Any]
    ok: bool
    result: Any | None = None
    error: str | None = None
