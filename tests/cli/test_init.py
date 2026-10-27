from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


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


def _scaffold_paths(root: Path, suite: str) -> list[Path]:
    evals = root / "evals" / suite
    return [
        evals / "suite.yaml",
        evals / "cases" / "t1.yaml",
        evals / "schema.json",
        evals / "cassettes" / "t1.jsonl",
        evals / "agent" / "agent.py",
        root / "baselines" / f"{suite}.json",
        root / ".github" / "workflows" / "runledger.yml",
    ]


def test_init_creates_demo_suite(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    evals_dir = tmp_path / "evals"
    result = _run_cli(
        ["init", "--path", str(evals_dir), "--suite", "demo"],
        cwd=root,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (evals_dir / "demo" / "suite.yaml").is_file()
    assert (evals_dir / "demo" / "cases" / "t1.yaml").is_file()
    assert (evals_dir / "demo" / "schema.json").is_file()
    assert (evals_dir / "demo" / "cassettes" / "t1.jsonl").is_file()
    assert (evals_dir / "demo" / "agent" / "agent.py").is_file()
    assert (tmp_path / "baselines" / "demo.json").is_file()
    workflow = tmp_path / ".github" / "workflows" / "runledger.yml"
    assert workflow.is_file()
    workflow_text = workflow.read_text(encoding="utf-8")
    assert 'runledger run "./evals/demo" --mode replay --baseline "./baselines/demo.json"' in workflow_text

    suite = yaml.safe_load((evals_dir / "demo" / "suite.yaml").read_text(encoding="utf-8"))
    case = yaml.safe_load((evals_dir / "demo" / "cases" / "t1.yaml").read_text(encoding="utf-8"))
    assert suite["mode"] == "replay"
    assert suite["budgets"]["max_tool_calls"] == 1
    assert suite["assertions"][0]["type"] == "json_schema"
    assert {"type": "call_order", "order": ["search_docs"]} in case["assertions"]

    baseline = json.loads((tmp_path / "baselines" / "demo.json").read_text(encoding="utf-8"))
    assert baseline["schema_version"] == 1
    assert baseline["aggregates"]["cases_pass"] == 1

    replay = _run_cli(
        [
            "run",
            str(evals_dir / "demo"),
            "--mode",
            "replay",
            "--baseline",
            str(tmp_path / "baselines" / "demo.json"),
        ],
        cwd=root,
    )
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert "PASS" in replay.stdout


def test_init_second_run_leaves_files_unchanged(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    evals_dir = tmp_path / "evals"
    first = _run_cli(
        ["init", "--path", str(evals_dir), "--suite", "demo"],
        cwd=root,
    )
    assert first.returncode == 0, first.stdout + first.stderr

    paths = _scaffold_paths(tmp_path, "demo")
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
    suite_path = evals_dir / "demo" / "suite.yaml"
    suite_path.write_bytes(before[suite_path][0] + b"\n# user edit\n")

    second = _run_cli(
        ["init", "--path", str(evals_dir), "--suite", "demo"],
        cwd=root,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert "Unchanged:" in second.stdout
    assert suite_path.read_bytes().endswith(b"# user edit\n")
    for path, (content, mtime_ns) in before.items():
        if path == suite_path:
            continue
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime_ns


def test_init_writes_missing_workflow_without_touching_suite(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    evals_dir = tmp_path / "evals"
    first = _run_cli(
        ["init", "--path", str(evals_dir), "--suite", "demo"],
        cwd=root,
    )
    assert first.returncode == 0, first.stdout + first.stderr

    workflow = tmp_path / ".github" / "workflows" / "runledger.yml"
    workflow.unlink()
    agent = evals_dir / "demo" / "agent" / "agent.py"
    agent.write_text(agent.read_text(encoding="utf-8") + "\n# keep\n", encoding="utf-8")
    baseline = (tmp_path / "baselines" / "demo.json").read_bytes()

    second = _run_cli(
        ["init", "--path", str(evals_dir), "--suite", "demo"],
        cwd=root,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert "# keep" in agent.read_text(encoding="utf-8")
    assert (tmp_path / "baselines" / "demo.json").read_bytes() == baseline
    assert 'runledger run "./evals/demo"' in workflow.read_text(encoding="utf-8")


def test_init_force_regenerates_scaffold(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    evals_dir = tmp_path / "evals"
    first = _run_cli(
        ["init", "--path", str(evals_dir), "--suite", "demo"],
        cwd=root,
    )
    assert first.returncode == 0, first.stdout + first.stderr

    agent = evals_dir / "demo" / "agent" / "agent.py"
    agent.write_text("changed\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "runledger.yml"
    workflow.write_text("name: custom\n", encoding="utf-8")

    second = _run_cli(
        ["init", "--path", str(evals_dir), "--suite", "demo", "--force"],
        cwd=root,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert "changed" not in agent.read_text(encoding="utf-8")
    assert "runledger run" in workflow.read_text(encoding="utf-8")


def test_init_creates_node_suite(tmp_path: Path) -> None:
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    root = Path(__file__).resolve().parents[2]
    evals_dir = tmp_path / "evals"
    result = _run_cli(
        ["init", "--path", str(evals_dir), "--suite", "node-demo", "--language", "node"],
        cwd=root,
    )

    assert result.returncode == 0
    assert (evals_dir / "node-demo" / "suite.yaml").is_file()
    assert (evals_dir / "node-demo" / "cases" / "t1.yaml").is_file()
    assert (evals_dir / "node-demo" / "schema.json").is_file()
    assert (evals_dir / "node-demo" / "cassettes" / "t1.jsonl").is_file()
    assert (evals_dir / "node-demo" / "agent" / "agent.js").is_file()
    assert (tmp_path / "baselines" / "node-demo.json").is_file()
    workflow = (tmp_path / ".github" / "workflows" / "runledger.yml").read_text(encoding="utf-8")
    assert 'runledger run "./evals/node-demo"' in workflow
    case = yaml.safe_load((evals_dir / "node-demo" / "cases" / "t1.yaml").read_text(encoding="utf-8"))
    assert {"type": "call_order", "order": ["search_docs"]} in case["assertions"]
