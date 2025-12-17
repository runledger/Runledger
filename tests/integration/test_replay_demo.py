from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path



def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "runledger", *args]
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
    )


def test_demo_replay_success() -> None:
    root = Path(__file__).resolve().parents[2]
    suite_dir = root / "examples" / "evals" / "demo"

    result = _run_cli(["run", str(suite_dir), "--mode", "replay"], cwd=root)

    assert result.returncode == 0
    assert "Artifacts written to:" in result.stdout

    run_dir = None
    for line in result.stdout.splitlines():
        if line.startswith("Artifacts written to:"):
            run_dir = line.split("Artifacts written to:", 1)[1].strip()
            break

    assert run_dir is not None
    run_path = (root / run_dir).resolve()
    summary_path = run_path / "summary.json"
    junit_path = run_path / "junit.xml"
    run_log_path = run_path / "run.jsonl"

    assert summary_path.is_file()
    assert junit_path.is_file()
    assert run_log_path.is_file()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["passed"] == 1
    assert summary["failed"] == 0


def test_demo_replay_schema_failure() -> None:
    root = Path(__file__).resolve().parents[2]
    suite_dir = root / "examples" / "evals" / "demo"
    schema_path = suite_dir / "schema.json"

    original = schema_path.read_text(encoding="utf-8")
    try:
        schema = json.loads(original)
        schema["required"] = ["category", "reply", "missing_field"]
        schema_path.write_text(json.dumps(schema), encoding="utf-8")

        result = _run_cli(["run", str(suite_dir), "--mode", "replay"], cwd=root)

        assert result.returncode == 1
        assert "FAIL" in result.stdout
    finally:
        schema_path.write_text(original, encoding="utf-8")
