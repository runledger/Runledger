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
    path.write_text(
        json.dumps(baseline.model_dump(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
