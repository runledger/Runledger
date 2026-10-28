from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from runledger.doctor import doctor_suite


@pytest.fixture
def suite_dir(tmp_path: Path) -> Path:
    (tmp_path / "cases").mkdir()
    (tmp_path / "agent.py").write_text("raise RuntimeError('must not execute')\n", encoding="utf-8")
    (tmp_path / "schema.json").write_text('{"type": "object"}', encoding="utf-8")
    (tmp_path / "empty.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "suite.yaml").write_text(
        yaml.safe_dump(
            {
                "suite_name": "doctor-test",
                "agent_command": [sys.executable, "agent.py"],
                "mode": "replay",
                "cases_path": "cases",
                "tool_registry": ["lookup"],
                "assertions": [{"type": "json_schema", "schema_path": "schema.json"}],
                "budgets": {"max_wall_ms": 1000, "max_tool_calls": 0, "max_tool_errors": 0},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "cases" / "one.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "one",
                "input": {},
                "cassette": "empty.jsonl",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def change(path: Path, **fields: object) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.update(fields)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def checks_named(result: dict, name: str, status: str) -> list[dict]:
    return [item for item in result["checks"] if item["name"] == name and item["status"] == status]


def test_valid_suite_with_empty_cassette_is_static_and_read_only(
    suite_dir: Path, monkeypatch
) -> None:
    marker = suite_dir / "executed"
    code = f"from pathlib import Path; Path({str(marker)!r}).touch()"
    change(
        suite_dir / "suite.yaml",
        agent_command=[sys.executable, "-c", code],
        tool_module="unsafe_user_module",
    )
    (suite_dir / "unsafe_user_module.py").write_text(code, encoding="utf-8")
    monkeypatch.syspath_prepend(str(suite_dir))
    before = {
        path.relative_to(suite_dir): path.read_bytes()
        for path in suite_dir.rglob("*")
        if path.is_file()
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("doctor attempted execution or a user-code import")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(importlib, "import_module", forbidden)
    result = doctor_suite(suite_dir)
    after = {
        path.relative_to(suite_dir): path.read_bytes()
        for path in suite_dir.rglob("*")
        if path.is_file()
    }
    assert result["ok"] is True
    assert result["schema_version"] == 1
    assert before == after
    assert not marker.exists()
    assert checks_named(result, "cassette", "pass")[0]["entries"] == 0
    assert checks_named(result, "dependency_readiness", "warning")
    assert code not in json.dumps(result)


@pytest.mark.parametrize("file", ["suite.yaml", "cases/one.yaml"])
def test_malformed_yaml_fails_without_echoing_source(suite_dir: Path, file: str) -> None:
    secret = "private-inline-code-and-token"
    (suite_dir / file).write_text(f"input: [\n {secret}: [", encoding="utf-8")
    result = doctor_suite(suite_dir)
    assert result["ok"] is False
    assert "Invalid YAML" in json.dumps(result)
    assert secret not in json.dumps(result)


@pytest.mark.parametrize("schema", ["{invalid-json", '{"type": "not-a-real-type"}'])
def test_bad_schema_is_detected_before_agent_runs(suite_dir: Path, schema: str) -> None:
    (suite_dir / "schema.json").write_text(schema, encoding="utf-8")
    result = doctor_suite(suite_dir)
    assert not result["ok"]
    assert checks_named(result, "json_schema", "fail")


def test_missing_schema(suite_dir: Path) -> None:
    (suite_dir / "schema.json").unlink()
    assert checks_named(doctor_suite(suite_dir), "json_schema", "fail")


def test_invalid_config_does_not_echo_argument_values(suite_dir: Path) -> None:
    secret = "private-argument-payload"
    change(suite_dir / "suite.yaml", agent_command=[sys.executable, {"token": secret}])
    result = doctor_suite(suite_dir)
    assert not result["ok"]
    assert checks_named(result, "suite_config", "fail")
    assert secret not in json.dumps(result)


def test_missing_suite_and_cases_directory(tmp_path: Path, suite_dir: Path) -> None:
    assert checks_named(doctor_suite(tmp_path / "missing-suite"), "suite_config", "fail")
    change(suite_dir / "suite.yaml", cases_path="missing-cases")
    assert checks_named(doctor_suite(suite_dir), "case_configs", "fail")


def test_external_schema_reference_is_not_fetched(suite_dir: Path, monkeypatch) -> None:
    import urllib.request

    def forbidden(*args, **kwargs):
        raise AssertionError("doctor fetched a schema reference")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    (suite_dir / "schema.json").write_text(
        '{"$ref": "https://invalid.example/schema.json"}', encoding="utf-8"
    )
    result = doctor_suite(suite_dir)
    assert result["ok"]
    assert checks_named(result, "schema_references", "warning")


@pytest.mark.parametrize(
    "assertion",
    [
        {"type": "typo_assertion"},
        {"type": "required_fields", "fields": "reply"},
        {"type": "must_call", "tools": [3]},
        {"type": "call_order", "order": ["unregistered"]},
        {"type": "json_schema"},
    ],
)
def test_unsupported_assertion_or_shape(suite_dir: Path, assertion: dict) -> None:
    change(suite_dir / "cases" / "one.yaml", assertions=[assertion])
    result = doctor_suite(suite_dir)
    assert not result["ok"]
    assert any(
        item["status"] == "fail" and item["name"] in {"assertion", "json_schema"}
        for item in result["checks"]
    )


def test_duplicate_ids_are_rejected(suite_dir: Path) -> None:
    original = suite_dir / "cases" / "one.yaml"
    (original.parent / "two.yaml").write_bytes(original.read_bytes())
    result = doctor_suite(suite_dir)
    assert not result["ok"]
    assert checks_named(result, "case_ids", "fail")


@pytest.mark.parametrize(
    "cassette",
    [
        "{broken-json",
        "[]",
        '{"tool":"lookup","args":{},"ok":"true"}',
        '{"tool":"unregistered","args":{},"ok":true}',
    ],
)
def test_bad_cassette_or_unregistered_tool(suite_dir: Path, cassette: str) -> None:
    (suite_dir / "empty.jsonl").write_text(cassette + "\n", encoding="utf-8")
    result = doctor_suite(suite_dir)
    assert not result["ok"]
    assert checks_named(result, "cassette", "fail")


@pytest.mark.parametrize("mode,ok", [("replay", False), ("record", True), ("live", True)])
def test_missing_cassette_depends_on_mode(suite_dir: Path, mode: str, ok: bool) -> None:
    (suite_dir / "empty.jsonl").unlink()
    change(suite_dir / "suite.yaml", mode=mode)
    result = doctor_suite(suite_dir)
    assert result["ok"] is ok


@pytest.mark.parametrize("value", [-1, "not-a-number", True, float("inf")])
def test_invalid_budget(suite_dir: Path, value: object) -> None:
    change(suite_dir / "suite.yaml", budgets={"max_wall_ms": value})
    assert not doctor_suite(suite_dir)["ok"]


def test_case_budgets_and_unenforced_limits(suite_dir: Path) -> None:
    change(suite_dir / "cases" / "one.yaml", budgets={"max_tool_calls": -1})
    assert checks_named(doctor_suite(suite_dir), "budgets", "fail")
    change(suite_dir / "cases" / "one.yaml", budgets={"max_tokens_out": 10, "max_cost_usd": 1.0})
    result = doctor_suite(suite_dir)
    assert result["ok"]
    assert len(checks_named(result, "budgets", "warning")) == 2


@pytest.mark.parametrize("baseline", [None, "invalid-json", "{}"])
def test_missing_or_invalid_baseline(suite_dir: Path, baseline: str | None) -> None:
    change(suite_dir / "suite.yaml", baseline_path="baseline.json")
    if baseline is not None:
        (suite_dir / "baseline.json").write_text(baseline, encoding="utf-8")
    result = doctor_suite(suite_dir)
    assert not result["ok"]
    assert checks_named(result, "baseline", "fail")


def test_missing_executable_does_not_expose_arguments(suite_dir: Path) -> None:
    secret = "inline-secret-token"
    change(
        suite_dir / "suite.yaml",
        agent_command=[str(suite_dir / "missing-program"), "--token", secret],
    )
    result = doctor_suite(suite_dir)
    assert checks_named(result, "agent_executable", "fail")
    assert secret not in json.dumps(result)


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable permission bits")
def test_nonexecutable_file_is_rejected(suite_dir: Path) -> None:
    agent = suite_dir / "agent.py"
    agent.chmod(0o600)
    change(suite_dir / "suite.yaml", agent_command=[str(agent)])
    assert checks_named(doctor_suite(suite_dir), "agent_executable", "fail")


def test_directory_cannot_be_executable(suite_dir: Path) -> None:
    change(suite_dir / "suite.yaml", agent_command=[str(suite_dir)])
    assert checks_named(doctor_suite(suite_dir), "agent_executable", "fail")


@pytest.mark.skipif(
    os.name != "nt", reason="Windows does not execute arbitrary script files directly"
)
def test_windows_script_needs_an_interpreter(suite_dir: Path) -> None:
    change(suite_dir / "suite.yaml", agent_command=[str(suite_dir / "agent.py")])
    assert checks_named(doctor_suite(suite_dir), "agent_executable", "fail")


def test_missing_interpreter_script_is_detected(suite_dir: Path) -> None:
    change(suite_dir / "suite.yaml", agent_command=[sys.executable, "-B", "missing-agent.py"])
    assert checks_named(doctor_suite(suite_dir), "agent_script", "fail")


def test_opaque_code_and_arguments_are_not_treated_as_files(suite_dir: Path) -> None:
    change(
        suite_dir / "suite.yaml",
        agent_command=[sys.executable, "-c", "print('not-a-file.py')", "missing.py"],
    )
    result = doctor_suite(suite_dir)
    assert result["ok"]
    assert not checks_named(result, "agent_script", "fail")


def test_module_dependencies_are_explicitly_unverified(suite_dir: Path) -> None:
    change(
        suite_dir / "suite.yaml",
        agent_command=[sys.executable, "-m", "module_that_is_not_installed"],
    )
    result = doctor_suite(suite_dir)
    assert result["ok"]
    assert checks_named(result, "dependency_readiness", "warning")


def test_checked_in_demo_has_no_false_failures(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(root)
    result = doctor_suite(root / "examples" / "evals" / "demo")
    assert result["ok"], result
    assert checks_named(result, "baseline", "pass")
