from __future__ import annotations

from pathlib import Path

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
