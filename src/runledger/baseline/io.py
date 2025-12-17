from __future__ import annotations

import json
from pathlib import Path

from .models import BaselineSummary


def load_baseline(path: Path) -> BaselineSummary:
    if not path.is_file():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return BaselineSummary.model_validate(data)


def write_baseline(path: Path, baseline: BaselineSummary) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = baseline.model_dump()
    cases = data.get("cases")
    if isinstance(cases, list):
        data["cases"] = sorted(cases, key=lambda case: str(case.get("id", "")))
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
