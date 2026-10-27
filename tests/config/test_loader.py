from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from runledger.config.loader import load_cases, load_suite


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_load_suite_from_dir(tmp_path: Path) -> None:
    suite_dir = tmp_path / "demo"
    suite_dir.mkdir()
    suite_yaml = suite_dir / "suite.yaml"
    _write_yaml(
        suite_yaml,
        {
            "suite_name": "demo",
            "agent_command": ["python", "agent.py"],
            "mode": "replay",
            "cases_path": "cases",
            "tool_registry": ["search_docs"],
        },
    )

    suite = load_suite(suite_dir)
    assert suite.suite_name == "demo"
    assert suite.cases_path == "cases"


def test_load_cases_orders_and_resolves_cassettes(tmp_path: Path) -> None:
    suite_dir = tmp_path / "demo"
    cases_dir = suite_dir / "cases"
    suite_dir.mkdir()
    cases_dir.mkdir()

    _write_yaml(
        cases_dir / "b.yaml",
        {"id": "b", "input": {}, "cassette": "cassettes/b.jsonl"},
    )
    _write_yaml(
        cases_dir / "a.yaml",
        {"id": "a", "input": {}, "cassette": "cassettes/a.jsonl"},
    )

    cases = load_cases(suite_dir, "cases")

    assert [case.id for case in cases] == ["a", "b"]
    assert cases[0].cassette == str((suite_dir / "cassettes/a.jsonl").resolve())


def test_windows_separators_resolve_to_existing_files(tmp_path: Path) -> None:
    suite_dir = tmp_path / "demo"
    cases_dir = suite_dir / "cases"
    (suite_dir / "cassettes").mkdir(parents=True)
    (suite_dir / "agent").mkdir(parents=True)
    cases_dir.mkdir()
    (suite_dir / "cassettes" / "t1.jsonl").write_text("{}\n", encoding="utf-8")
    (suite_dir / "agent" / "agent.py").write_text("print('ok')\n", encoding="utf-8")
    (suite_dir / "schema.json").write_text("{}\n", encoding="utf-8")
    (suite_dir / "suite.yaml").write_text(
        "\n".join(
            [
                "suite_name: demo",
                "agent_command:",
                "  - python3",
                "  - agent\\agent.py",
                "mode: replay",
                "cases_path: cases",
                "tool_registry:",
                "  - search_docs",
                "baseline_path: ..\\baselines\\demo.json",
                "assertions:",
                "  - type: json_schema",
                "    schema_path: schema.json",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (cases_dir / "t1.yaml").write_text(
        "id: t1\ninput: {}\ncassette: cassettes\\t1.jsonl\n",
        encoding="utf-8",
    )

    suite = load_suite(suite_dir)
    cases = load_cases(suite_dir, suite.cases_path)

    assert Path(suite.agent_command[1]) == (suite_dir / "agent" / "agent.py").resolve()
    assert suite.baseline_path is not None
    assert Path(suite.baseline_path) == (tmp_path / "baselines" / "demo.json").resolve()
    schema_path = suite.assertions[0].schema_path
    assert isinstance(schema_path, str)
    assert Path(schema_path) == (suite_dir / "schema.json").resolve()
    assert Path(cases[0].cassette) == (suite_dir / "cassettes" / "t1.jsonl").resolve()


@pytest.mark.parametrize("pattern, matched", [(r"\d+", "True"), (".", "False")])
def test_agent_inline_code_and_regex_arguments_are_preserved(
    tmp_path: Path, pattern: str, matched: str
) -> None:
    code = r'import re, sys; print(bool(re.fullmatch(sys.argv[1], "42"))); print("first\nsecond")'
    command = [sys.executable, "-c", code, pattern]
    _write_yaml(
        tmp_path / "suite.yaml",
        {
            "suite_name": "inline",
            "agent_command": command,
            "mode": "replay",
            "cases_path": "cases",
            "tool_registry": [],
        },
    )

    suite = load_suite(tmp_path)
    assert suite.agent_command[1:] == command[1:]
    result = subprocess.run(suite.agent_command, capture_output=True, text=True, check=True)
    assert result.stdout.splitlines() == [matched, "first", "second"]


def test_unknown_regression_threshold_is_rejected(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "suite.yaml",
        {
            "suite_name": "demo",
            "agent_command": ["python", "agent.py"],
            "mode": "replay",
            "cases_path": "cases",
            "tool_registry": [],
            "regression": {"max_p95_wall_ms_delta_pctx": 0.1},
        },
    )

    with pytest.raises(ValueError, match="max_p95_wall_ms_delta_pctx"):
        load_suite(tmp_path)


def test_inline_code_is_not_resolved_as_an_existing_file(tmp_path: Path) -> None:
    (tmp_path / "pass").write_text("not Python code", encoding="utf-8")
    _write_yaml(
        tmp_path / "suite.yaml",
        {
            "suite_name": "inline",
            "agent_command": [sys.executable, "-c", "pass"],
            "mode": "replay",
            "cases_path": "cases",
            "tool_registry": [],
        },
    )

    suite = load_suite(tmp_path)
    assert suite.agent_command[-1] == "pass"
    subprocess.run(suite.agent_command, capture_output=True, check=True)


def test_regression_threshold_aliases_remain_supported(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "suite.yaml",
        {
            "suite_name": "demo",
            "agent_command": ["python", "agent.py"],
            "mode": "replay",
            "cases_path": "cases",
            "tool_registry": [],
            "regression": {"min_success_rate": 1.0, "max_p95_wall_ms_increase_pct": 0.1},
        },
    )

    suite = load_suite(tmp_path)
    assert suite.regression is not None
    assert suite.regression.min_pass_rate == 1.0
    assert suite.regression.max_p95_wall_ms_delta_pct == 0.1


def test_invalid_yaml_includes_parser_detail(tmp_path: Path) -> None:
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text("suite_name: [\n  broken\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        load_suite(suite_path)

    message = str(exc_info.value)
    assert f"Invalid YAML in {suite_path}" in message
    assert message != f"Invalid YAML in {suite_path}"
    assert "line" in message.lower() or "expected" in message.lower()
