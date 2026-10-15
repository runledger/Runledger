"""Quickstart coverage for machines that do not have `python` on PATH."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _env_with_path(bin_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = str(bin_dir)
    env["PYTHONPATH"] = str(ROOT / "src")
    # Avoid inheriting a venv's bin directory via PYTHONHOME or similar.
    env.pop("PYTHONHOME", None)
    return env


def _run_module(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "runledger", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


def _assert_no_traceback(result: subprocess.CompletedProcess[str]) -> None:
    combined = result.stdout + result.stderr
    assert "Traceback (most recent call last)" not in combined
    assert "FileNotFoundError" not in combined


def _link_interpreter(bin_dir: Path, name: str) -> None:
    target = shutil.which("python3") or sys.executable
    link = bin_dir / name
    link.symlink_to(target)


def _write_min_suite(suite_dir: Path, agent_command: list[str]) -> None:
    cases = suite_dir / "cases"
    cassettes = suite_dir / "cassettes"
    cases.mkdir(parents=True)
    cassettes.mkdir()
    (cassettes / "t1.jsonl").write_text(
        json.dumps(
            {"tool": "search_docs", "args": {"q": "x"}, "ok": True, "result": {}},
        )
        + "\n",
        encoding="utf-8",
    )
    (cases / "t1.yaml").write_text(
        "\n".join(
            [
                "id: t1",
                "description: triage",
                "input:",
                "  ticket: x",
                "cassette: cassettes/t1.jsonl",
                "",
            ]
        ),
        encoding="utf-8",
    )
    suite = {
        "suite_name": "demo",
        "agent_command": agent_command,
        "mode": "replay",
        "cases_path": "cases",
        "tool_registry": ["search_docs"],
    }
    (suite_dir / "suite.yaml").write_text(yaml.safe_dump(suite, sort_keys=False), encoding="utf-8")


def test_quickstart_without_python_on_path(tmp_path: Path) -> None:
    """README quickstart must pass when PATH contains python3 and not python."""
    if shutil.which("python3") is None and not sys.executable:
        pytest.skip("no python3 interpreter available to simulate a python3-only PATH")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _link_interpreter(bin_dir, "python3")
    assert not (bin_dir / "python").exists()
    env = _env_with_path(bin_dir)

    probe = subprocess.run(
        ["/bin/sh", "-c", "command -v python || true; printf '\\n---\\n'; command -v python3"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    before, _, after = probe.stdout.partition("---")
    assert before.strip() == ""
    assert after.strip().endswith("python3")

    work = tmp_path / "work"
    work.mkdir()
    init = _run_module(["init"], cwd=work, env=env)
    assert init.returncode == 0, init.stdout + init.stderr
    _assert_no_traceback(init)

    suite_path = work / "evals" / "demo" / "suite.yaml"
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    assert suite["agent_command"] == ["python3", "agent/agent.py"]
    assert (work / "baselines" / "demo.json").is_file()

    run = _run_module(
        ["run", "./evals/demo", "--mode", "replay", "--baseline", "baselines/demo.json"],
        cwd=work,
        env=env,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    _assert_no_traceback(run)
    assert "PASS" in run.stdout


def test_quickstart_uses_python_when_python3_is_absent(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _link_interpreter(bin_dir, "python")
    env = _env_with_path(bin_dir)
    work = tmp_path / "work"
    work.mkdir()

    init = _run_module(["init"], cwd=work, env=env)
    assert init.returncode == 0, init.stdout + init.stderr
    suite = yaml.safe_load((work / "evals" / "demo" / "suite.yaml").read_text(encoding="utf-8"))
    assert suite["agent_command"][0] == "python"

    run = _run_module(
        ["run", "./evals/demo", "--mode", "replay", "--baseline", "baselines/demo.json"],
        cwd=work,
        env=env,
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_quickstart_falls_back_to_running_interpreter(tmp_path: Path) -> None:
    bin_dir = tmp_path / "empty-bin"
    bin_dir.mkdir()
    env = _env_with_path(bin_dir)
    work = tmp_path / "work"
    work.mkdir()

    init = _run_module(["init"], cwd=work, env=env)
    assert init.returncode == 0, init.stdout + init.stderr
    suite = yaml.safe_load((work / "evals" / "demo" / "suite.yaml").read_text(encoding="utf-8"))
    assert suite["agent_command"][0] == sys.executable

    run = _run_module(
        ["run", "./evals/demo", "--mode", "replay", "--baseline", "baselines/demo.json"],
        cwd=work,
        env=env,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    _assert_no_traceback(run)


def test_run_missing_agent_command_has_no_traceback(tmp_path: Path) -> None:
    suite_dir = tmp_path / "evals" / "demo"
    _write_min_suite(suite_dir, ["python", "agent/agent.py"])
    env = _env_with_path(tmp_path / "empty-bin")
    (tmp_path / "empty-bin").mkdir()

    result = _run_module(
        ["run", str(suite_dir), "--mode", "replay"],
        cwd=tmp_path,
        env=env,
    )
    assert result.returncode == 1
    _assert_no_traceback(result)
    combined = result.stdout + result.stderr
    assert "Agent command not found: 'python'" in combined
    assert "python3" in combined
    assert "suite.yaml" in combined
    assert "PATH" in combined


def test_run_unrunnable_agent_command_has_no_traceback(tmp_path: Path) -> None:
    program = tmp_path / "agent-bin"
    program.write_text("not a program\n", encoding="utf-8")
    program.chmod(0o644)
    suite_dir = tmp_path / "evals" / "demo"
    _write_min_suite(suite_dir, [str(program)])

    result = _run_module(
        ["run", str(suite_dir), "--mode", "replay"],
        cwd=tmp_path,
        env=os.environ.copy() | {"PYTHONPATH": str(ROOT / "src")},
    )
    assert result.returncode == 1
    _assert_no_traceback(result)
    combined = result.stdout + result.stderr
    assert "not executable" in combined
    assert str(program) in combined
    assert "suite.yaml" in combined


def test_init_unrunnable_python3_does_not_traceback(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    bad = bin_dir / "python3"
    bad.write_bytes(b"\x7fELF\x00not-a-real-binary")
    bad.chmod(0o755)
    env = _env_with_path(bin_dir)
    work = tmp_path / "work"
    work.mkdir()

    init = _run_module(["init"], cwd=work, env=env)
    assert init.returncode == 1
    _assert_no_traceback(init)
    combined = init.stdout + init.stderr
    assert "Failed to generate baseline" in combined
    assert "python3" in combined
    assert not (work / "baselines" / "demo.json").exists()
