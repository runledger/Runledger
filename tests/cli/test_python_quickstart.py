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


@pytest.mark.skipif(os.name == "nt", reason="POSIX python3-only PATH and symlink fixture")
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
    if os.name == "nt":
        # A real Windows launcher needs its venv metadata; a renamed executable
        # or POSIX symlink is not a faithful Python installation on Windows.
        venv_dir = tmp_path / "python-only"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(venv_dir)],
            check=True,
            capture_output=True,
        )
        bin_dir = venv_dir / "Scripts"
    else:
        bin_dir.mkdir()
        _link_interpreter(bin_dir, "python")
    env = _env_with_path(bin_dir)
    assert shutil.which("python", path=env["PATH"]) is not None
    assert shutil.which("python3", path=env["PATH"]) is None
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX python3-only PATH and symlink fixture")
def test_bare_python_runs_when_only_python3_is_on_path(tmp_path: Path) -> None:
    """Suites that still say `python` must run on Ubuntu, where only python3 exists."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _link_interpreter(bin_dir, "python3")
    env = _env_with_path(bin_dir)
    suite_dir = tmp_path / "evals" / "demo"
    _write_min_suite(suite_dir, ["python", "agent/agent.py"])
    agent_dir = suite_dir / "agent"
    agent_dir.mkdir()
    (agent_dir / "agent.py").write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "",
                "def send(payload):",
                "    sys.stdout.write(json.dumps(payload) + '\\n')",
                "    sys.stdout.flush()",
                "",
                "def main():",
                "    for line in sys.stdin:",
                "        line = line.strip()",
                "        if not line:",
                "            continue",
                "        msg = json.loads(line)",
                "        if msg.get('type') == 'task_start':",
                "            send({'type': 'tool_call', 'name': 'search_docs', 'call_id': 'c1', 'args': {'q': 'x'}})",
                "        elif msg.get('type') == 'tool_result':",
                "            send({'type': 'final_output', 'output': {'category': 'account', 'reply': 'ok'}})",
                "            return 0",
                "    return 1",
                "",
                "if __name__ == '__main__':",
                "    raise SystemExit(main())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_module(["run", str(suite_dir), "--mode", "replay"], cwd=tmp_path, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_checked_in_demo_uses_python3() -> None:
    suite = yaml.safe_load((ROOT / "examples" / "evals" / "demo" / "suite.yaml").read_text(encoding="utf-8"))
    assert suite["agent_command"][0] == "python3"


@pytest.mark.parametrize(
    "program",
    [
        "runledger-test-missing-agent-command",
        pytest.param(
            "python",
            marks=pytest.mark.skipif(
                os.name == "nt",
                reason="Windows also searches the calling executable directory, outside PATH",
            ),
        ),
    ],
)
def test_run_missing_agent_command_has_no_traceback(tmp_path: Path, program: str) -> None:
    suite_dir = tmp_path / "evals" / "demo"
    _write_min_suite(suite_dir, [program, "agent/agent.py"])
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
    assert f"Agent command not found: {program!r}" in combined
    assert "python3" in combined
    assert "suite.yaml" in combined
    assert "PATH" in combined


@pytest.mark.skipif(os.name == "nt", reason="POSIX execute permission bits")
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX ELF executable and permission fixture")
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


@pytest.mark.skipif(os.name != "nt", reason="Windows executable format")
def test_windows_invalid_executable_has_no_traceback(tmp_path: Path) -> None:
    program = tmp_path / "agent.exe"
    program.write_bytes(b"not a Windows executable")
    suite_dir = tmp_path / "evals" / "demo"
    _write_min_suite(suite_dir, [str(program)])

    result = _run_module(
        ["run", str(suite_dir), "--mode", "replay"],
        cwd=tmp_path,
        env=os.environ.copy() | {"PYTHONPATH": str(ROOT / "src")},
    )

    assert result.returncode == 1
    _assert_no_traceback(result)
    assert "Failed to start agent command" in result.stdout + result.stderr
    assert repr(str(program)) in result.stdout + result.stderr
