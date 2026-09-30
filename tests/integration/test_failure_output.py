from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _make_suite(tmp_path: Path) -> Path:
    src = ROOT / "examples" / "evals" / "demo"
    suite_dir = tmp_path / "suite"
    shutil.copytree(src, suite_dir)
    suite_yaml = suite_dir / "suite.yaml"
    suite = yaml.safe_load(suite_yaml.read_text(encoding="utf-8"))
    suite["agent_command"] = [sys.executable, str(ROOT / "examples" / "demo_agent_py" / "agent.py")]
    suite.pop("baseline_path", None)
    suite["assertions"].append({"type": "call_order", "order": ["lookup_order", "search_docs"]})
    suite_yaml.write_text(yaml.safe_dump(suite, sort_keys=False), encoding="utf-8")
    return suite_dir


def _run(tmp_path: Path, suite_dir: Path, *, github: bool, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("GITHUB_ACTIONS", None)
    env["COLUMNS"] = "200"
    if github:
        env["GITHUB_ACTIONS"] = "true"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "runledger",
            "run",
            str(suite_dir),
            "--mode",
            "replay",
            "--output-dir",
            str(tmp_path / "out"),
            *(extra or []),
        ],
        cwd=suite_dir,
        env=env,
        text=True,
        capture_output=True,
    )


def test_run_prints_failure_reason(tmp_path: Path) -> None:
    suite_dir = _make_suite(tmp_path)
    result = _run(tmp_path, suite_dir, github=False)

    assert result.returncode == 1
    out = result.stdout
    assert "FAIL t1" in out
    assert "assertion: call_order" in out
    assert "message:   Tool call order not satisfied: lookup_order -> search_docs" in out
    assert "expected:  lookup_order -> search_docs" in out
    assert "observed:  search_docs" in out
    assert "::error" not in out
    # Reasons come after the results table.
    assert out.index("RunLedger Results") < out.index("FAIL t1")


def test_run_emits_github_annotation(tmp_path: Path) -> None:
    suite_dir = _make_suite(tmp_path)
    result = _run(tmp_path, suite_dir, github=True)

    assert result.returncode == 1
    assert (
        "::error title=runledger: t1::Tool call order not satisfied: lookup_order -> search_docs"
        in result.stdout.splitlines()
    )


def test_gate_failure_reason_printed(tmp_path: Path) -> None:
    suite_dir = _make_suite(tmp_path)
    baseline = ROOT / "baselines" / "demo.json"
    result = _run(tmp_path, suite_dir, github=True, extra=["--baseline", str(baseline)])

    assert result.returncode == 1
    assert "Gate failures" in result.stdout
    assert "min_pass_rate: Regression gate min_pass_rate failed: pass_rate 0.0000 < required 1.0000" in result.stdout
    assert any(
        line.startswith("::error title=runledger: gate min_pass_rate::")
        for line in result.stdout.splitlines()
    )


def test_passing_run_prints_no_failure_block(tmp_path: Path) -> None:
    src = ROOT / "examples" / "evals" / "demo"
    env = os.environ.copy()
    env["GITHUB_ACTIONS"] = "true"
    result = subprocess.run(
        [sys.executable, "-m", "runledger", "run", str(src), "--mode", "replay", "--output-dir", str(tmp_path / "out")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert "Failures (" not in result.stdout
    assert "::error" not in result.stdout
