from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(cwd / "src"))
    return subprocess.run(
        [sys.executable, "-m", "runledger", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
    )


def test_init_creates_demo_suite(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    evals_dir = tmp_path / "evals"
    result = _run_cli(
        ["init", "--path", str(evals_dir), "--suite", "demo"],
        cwd=root,
    )

    assert result.returncode == 0
    assert (evals_dir / "demo" / "suite.yaml").is_file()
    assert (evals_dir / "demo" / "cases" / "t1.yaml").is_file()
    assert (evals_dir / "demo" / "schema.json").is_file()
    assert (evals_dir / "demo" / "cassettes" / "t1.jsonl").is_file()
    assert (evals_dir / "demo" / "agent" / "agent.py").is_file()
    assert (tmp_path / "baselines" / "demo.json").is_file()

    baseline = json.loads((tmp_path / "baselines" / "demo.json").read_text(encoding="utf-8"))
    assert baseline["schema_version"] == 1
