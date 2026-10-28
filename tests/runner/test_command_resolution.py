from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

from runledger.runner import subprocess as runner


def _executable(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == "nt" and not name.lower().endswith(".exe"):
        name += ".exe"
    executable = directory / name
    executable.touch()
    executable.chmod(0o755)
    return executable


def _assert_resolved(command: list[str], executable: Path, arguments: list[str]) -> None:
    assert Path(command[0]).is_absolute()
    assert Path(command[0]) == executable
    assert command[1:] == arguments


@pytest.mark.parametrize("alias", ["python", "python3", "python.exe", "python3.exe"])
def test_alias_resolves_against_child_path(alias: str, tmp_path: Path, monkeypatch) -> None:
    parent = _executable(tmp_path / "parent", alias)
    selected = _executable(tmp_path / "child", alias)
    monkeypatch.setenv("PATH", str(parent.parent))
    environment = {"PATH": str(selected.parent)}
    arguments = ["agent with spaces.py", r"C:\literal\new\test", "$HOME", "a;b", 'a"b']
    command = [alias, *arguments]

    _assert_resolved(runner.resolve_agent_command(command, environment), selected, arguments)
    assert command == [alias, *arguments]
    assert environment == {"PATH": str(selected.parent)}


@pytest.mark.parametrize(
    ("requested", "available"),
    [
        ("python", "python3"),
        ("python3", "python"),
        ("python.exe", "python3"),
        ("python3.exe", "python"),
    ],
)
def test_python_alias_fallback_is_absolute(requested: str, available: str, tmp_path: Path) -> None:
    selected = _executable(tmp_path, available)
    _assert_resolved(
        runner.resolve_agent_command([requested, "agent.py"], {"PATH": str(tmp_path)}),
        selected,
        ["agent.py"],
    )


def test_default_environment_uses_current_path(tmp_path: Path, monkeypatch) -> None:
    selected = _executable(tmp_path, "python")
    monkeypatch.setenv("PATH", str(tmp_path))
    _assert_resolved(runner.resolve_agent_command(["python"]), selected, [])


def test_relative_path_entry_becomes_absolute_without_following_symlinks(
    tmp_path: Path, monkeypatch
) -> None:
    selected = _executable(tmp_path / "relative bin", "python")
    monkeypatch.chdir(tmp_path)
    _assert_resolved(
        runner.resolve_agent_command(["python"], {"PATH": "relative bin"}), selected, []
    )


@pytest.mark.skipif(os.name == "nt", reason="symlinks need special privileges on Windows")
def test_selected_python_symlink_is_preserved(tmp_path: Path) -> None:
    selected = tmp_path / "python"
    selected.symlink_to(sys.executable)
    _assert_resolved(
        runner.resolve_agent_command(["python"], {"PATH": str(tmp_path)}), selected, []
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows environment keys are case-insensitive")
@pytest.mark.parametrize("path_key", ["Path", "path", "pAtH"])
def test_windows_path_key_is_case_insensitive(path_key: str, tmp_path: Path) -> None:
    selected = _executable(tmp_path, "python")
    _assert_resolved(
        runner.resolve_agent_command(["python"], {path_key: str(tmp_path)}), selected, []
    )


@pytest.mark.parametrize(
    "command",
    [
        [],
        ["missing-agent", "--literal"],
        ["node", "app.js"],
        ["./python", "arg"],
        ["../bin/python3", "arg"],
        [r".\python.exe", "arg"],
        [r"C:\tools\python.exe", "arg"],
        ["/opt/python/bin/python", "arg"],
    ],
)
def test_non_aliases_and_explicit_paths_are_unchanged(command: list[str], monkeypatch) -> None:
    def unexpected_lookup(*args, **kwargs):
        pytest.fail("Explicit paths and non-Python programs must not be searched")

    monkeypatch.setattr(runner.shutil, "which", unexpected_lookup)
    assert runner.resolve_agent_command(command, {"PATH": "ignored"}) == command


def test_missing_alias_retains_original_command(tmp_path: Path) -> None:
    command = ["python3", "agent.py"]
    assert runner.resolve_agent_command(command, {"PATH": str(tmp_path)}) == command


def test_missing_child_path_does_not_inherit_parent_path(monkeypatch) -> None:
    searched = []

    def which(program, *, path):
        searched.append((program, path))

    monkeypatch.setenv("PATH", "parent-only-bin")
    monkeypatch.setattr(runner.shutil, "which", which)
    assert runner.resolve_agent_command(["python"], {}) == ["python"]
    assert searched == [("python", os.defpath), ("python3", os.defpath)]


@pytest.mark.parametrize("alias", ["python", "python3"])
def test_agent_uses_separate_venv_selected_by_child_path(alias: str, tmp_path: Path) -> None:
    """A bare launcher must import a dependency available only in the child venv."""
    selected_venv = tmp_path / "selected environment"
    venv.EnvBuilder(with_pip=False).create(selected_venv)
    bin_dir = selected_venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"PATH", "PYTHONHOME", "PYTHONPATH"}
    }
    environment["Path" if os.name == "nt" else "PATH"] = str(bin_dir)
    purelib = subprocess.run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    ).stdout.strip()
    sentinel = Path(purelib) / "runledger_selected_venv_sentinel.py"
    sentinel.write_text("VALUE = 'dependency from selected environment'\n", encoding="utf-8")
    script = (
        "import json, sys, runledger_selected_venv_sentinel as dependency; "
        "print(json.dumps({'type': 'final_output', 'output': {"
        "'dependency': dependency.VALUE, 'prefix': sys.prefix, 'executable': sys.executable, "
        "'module': dependency.__file__, 'args': sys.argv[1:]}}), flush=True)"
    )
    arguments = ["space separated", r"C:\literal\new\test", "$HOME", "a;b", 'a"b']
    with runner.AgentProcess(
        [alias, "-c", script, *arguments], env=environment, timeout_s=10
    ) as agent:
        output = agent.recv().output

    assert output["dependency"] == "dependency from selected environment"
    assert Path(output["prefix"]).samefile(selected_venv)
    assert Path(output["executable"]).samefile(python)
    assert Path(output["module"]).samefile(sentinel)
    assert output["args"] == arguments
