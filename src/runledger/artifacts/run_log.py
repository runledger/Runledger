from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from runledger.runner.models import CaseResult
from runledger.util.redaction import redact


def write_run_log(run_dir: Path, cases: Iterable[CaseResult]) -> Path:
    run_path = run_dir / "run.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)

    with run_path.open("w", encoding="utf-8") as handle:
        for case in cases:
            for event in case.trace:
                event = redact(event)
                handle.write(
                    json.dumps(event, separators=(",", ":"), ensure_ascii=False)
                    + "\n"
                )

    return run_path
