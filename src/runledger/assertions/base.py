from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssertionFailure:
    type: str
    message: str
    details: dict[str, Any] | None = None
