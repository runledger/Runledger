from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest
import yaml

from runledger.config.loader import load_suite, resolve_command_paths
from runledger.verification import load_plan, verify_suite


def test_executable_keeps_lexical_path_while_arguments_still_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cover Windows reparse-point semantics without requiring symlink privileges."""
    executable = tmp_path / "venv" / "python.exe"
    executable.parent.mkdir()
    executable.write_text("interpreter placeholder", encoding="utf-8")
    base_executable = tmp_path / "base-python.exe"
    original_resolve = Path.resolve

    def resolve(path: Path, *args, **kwargs) -> Path:
        if path == executable:
            return base_executable
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    command = resolve_command_paths(["venv/python.exe", "venv/python.exe"], tmp_path)
    assert command[0] == os.path.abspath(executable)
    assert command[1] == str(base_executable)


def test_suite_and_plan_explicit_interpreter_retain_venv_dependencies(tmp_path: Path) -> None:
    """A POSIX venv symlink must not become the base Python during config loading."""
    environment = tmp_path / "isolated venv"
    venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if os.name != "nt":
        assert python.is_symlink(), "Fixture must exercise the POSIX venv symlink"
    purelib = Path(
        subprocess.check_output(
            [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True,
        ).strip()
    )
    purelib.mkdir(parents=True, exist_ok=True)
    (purelib / "runledger_venv_sentinel.py").write_text("VALUE = 'venv-only'\n", encoding="utf-8")
    agent = tmp_path / "agent.py"
    agent.write_text(
        "import json, sys\n"
        "from runledger_venv_sentinel import VALUE\n"
        "task = json.loads(sys.stdin.readline())\n"
        "output = {} if task['input'].get('omit') else {'marker': VALUE}\n"
        "print(json.dumps({'type': 'final_output', 'output': output}), flush=True)\n",
        encoding="utf-8",
    )
    suite = tmp_path / "suite.yaml"
    suite.write_text(
        yaml.safe_dump(
            {
                "suite_name": "venv-resolution",
                "mode": "replay",
                "cases_path": "cases",
                "agent_command": [str(python), str(agent)],
                "tool_registry": [],
                "assertions": [{"type": "required_fields", "fields": ["marker"]}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "c1.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "c1",
                "input": {"omit": False},
                "cassette": "empty.jsonl",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "empty.jsonl").write_text("", encoding="utf-8")
    plan = tmp_path / "verification.yaml"
    plan.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "regressions": [
                    {
                        "name": "missing-marker",
                        "case_id": "c1",
                        "agent_command": [str(python), str(agent)],
                        "input": {"omit": True},
                        "expect": {
                            "assertion": "required_fields",
                            "details": {"missing": ["marker"]},
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert load_suite(suite).agent_command[0] == os.path.abspath(python)
    assert load_plan(plan).regressions[0].agent_command[0] == os.path.abspath(python)
    report = verify_suite(suite, plan, repeats=2, output_dir=tmp_path / "out")
    assert report["passed"], report
    assert all(check["passed"] for check in report["checks"])
    events = Path(report["artifact_directory"]) / "unchanged-01" / "run.jsonl"
    outputs = [
        json.loads(line)["output"]
        for line in events.read_text().splitlines()
        if json.loads(line)["type"] == "final_output"
    ]
    assert outputs == [{"marker": "venv-only"}]


def test_module_name_stays_literal_when_local_package_exists(tmp_path: Path) -> None:
    package = tmp_path / "sample_package"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "import json, sys; print(json.dumps(sys.argv[1:]))", encoding="utf-8"
    )
    argument = tmp_path / "data.txt"
    argument.write_text("example", encoding="utf-8")
    command = resolve_command_paths([sys.executable, "-m", "sample_package", "data.txt"], tmp_path)
    assert command[2] == "sample_package"
    assert command[3] == str(argument.resolve())
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == [str(argument.resolve())]


def test_node_print_code_stays_literal_when_it_matches_local_filename(tmp_path: Path) -> None:
    # No Node installation is needed to verify argv preservation; "process.cwd()"
    # is both valid inline JavaScript and a valid filename on supported platforms.
    code = "process.cwd()"
    (tmp_path / code).write_text("not a JavaScript argument", encoding="utf-8")
    command = ["node", "-p", code]
    assert resolve_command_paths(command, tmp_path) == command
