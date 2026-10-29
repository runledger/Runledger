from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "openchatbi_capture", ROOT / "examples/openchatbi-handoff/capture.py"
)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


@pytest.fixture
def trace():
    return [
        {"type": "task_start", "input": {"prompt": "schema discovery"}},
        {"type": "tool_call", "call_id": "real-id", "name": "search_schema", "args": {}},
        {"type": "tool_result", "call_id": "real-id", "ok": True, "result": {"tables": []}},
        {"type": "final_output", "output": {"category": "bi", "reply": "done"}},
        {"type": "case_end", "passed": True},
    ]


def write_trace(path, events):
    path.write_text(
        "".join(json.dumps({"case_id": capture.CASE_ID, **event}) + "\n" for event in events),
        encoding="utf-8",
    )
    return path


def test_accepts_complete_serial_capture_and_unknown_effects(tmp_path, trace):
    result = capture.validate_capture(write_trace(tmp_path / "run.jsonl", trace))
    assert result == {
        "events": 3,
        "tool_calls": 1,
        "responses": 1,
        "complete_serial_trace": True,
        "effects_complete": False,
    }


def test_accepts_complete_skipped_tool_capture(tmp_path, trace):
    result = capture.validate_capture(write_trace(tmp_path / "run.jsonl", [trace[0], *trace[3:]]))
    assert result["tool_calls"] == result["responses"] == 0


@pytest.mark.parametrize(
    "mutation",
    ["missing-response", "concurrent", "missing-end", "duplicate-start", "effect", "error"],
)
def test_rejects_incomplete_unsupported_or_unproven_traces(tmp_path, trace, mutation):
    if mutation == "missing-response":
        del trace[2]
    elif mutation == "concurrent":
        trace.insert(
            2, {"type": "tool_call", "call_id": "another", "name": "search_schema", "args": {}}
        )
    elif mutation == "missing-end":
        trace.pop()
    elif mutation == "duplicate-start":
        trace.insert(1, trace[0].copy())
    elif mutation == "effect":
        trace.insert(
            3, {"type": "business_effect", "call_id": "real-id", "effect": {"type": "invented"}}
        )
    else:
        trace[3] = {"type": "task_error", "message": "failed"}
    with pytest.raises(ValueError):
        capture.validate_capture(write_trace(tmp_path / "run.jsonl", trace))


def verification_report():
    fingerprints = [{"case_id": capture.CASE_ID, "sha256": "b" * 64}]
    return {
        "passed": True,
        "checks": [
            {"name": "unchanged-01", "passed": True, "behavior_sha256": fingerprints},
            {
                "name": "unchanged-02",
                "passed": True,
                "behavior_sha256": copy.deepcopy(fingerprints),
            },
            {
                "name": "regression-01-skip-schema",
                "passed": True,
                "actual_failure_type": "assertion_failed",
                "tool_calls": 0,
            },
            {
                "name": "recovery-01-skip-schema",
                "passed": True,
                "behavior_sha256": copy.deepcopy(fingerprints),
            },
        ],
    }


def test_verification_requires_specific_failure_and_recovered_hash():
    report = verification_report()
    assert capture.validate_verification(report)["aggregate_checks"] == 4
    report["checks"][3]["behavior_sha256"][0]["sha256"] = "c" * 64
    with pytest.raises(ValueError, match="behavior differ"):
        capture.validate_verification(report)


def test_verification_rejects_startup_failure_even_if_report_says_passed():
    report = verification_report()
    report["checks"][2]["actual_failure_type"] = "agent_error"
    with pytest.raises(ValueError, match="unrelated"):
        capture.validate_verification(report)


def test_child_environment_excludes_credentials_and_user_config(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-forward")
    monkeypatch.setenv("PYTHONPATH", "other-source")
    monkeypatch.setenv("CONFIG_FILE", "live-config.yaml")
    environment = capture.runtime_environment(tmp_path)
    assert "OPENAI_API_KEY" not in environment
    assert "PYTHONPATH" not in environment
    assert environment["CONFIG_FILE"] == str(tmp_path / "missing-openchatbi-config.yaml")
    assert environment["LANGSMITH_TRACING"] == "false"


def test_prepared_fixture_preserves_source_schema_and_budget(tmp_path):
    repo = tmp_path / "repo"
    source = repo / "evals/runledger"
    (source / "cases").mkdir(parents=True)
    suite = {
        "suite_name": "openchatbi",
        "mode": "replay",
        "agent_command": ["python", "agent.py"],
        "cases_path": "cases",
        "tool_registry": ["search_schema"],
        "assertions": [{"type": "json_schema", "schema_path": "schema.json"}],
        "budgets": {"max_wall_ms": 20000, "max_tool_calls": 1},
        "baseline_path": "old-baseline.json",
        "regression": {"min_pass_rate": 1.0},
    }
    (source / "suite.yaml").write_text(yaml.safe_dump(suite), encoding="utf-8")
    (source / "schema.json").write_text('{"type":"object","required":["reply"]}', encoding="utf-8")
    (source / "cassette.jsonl").write_text(
        '{"tool":"search_schema","args":{},"ok":true,"result":{}}\n', encoding="utf-8"
    )
    (source / "cases/c21_schema_discovery.yaml").write_text(
        yaml.safe_dump(
            {
                "id": capture.CASE_ID,
                "description": "schema",
                "input": {"prompt": "schema"},
                "cassette": "cassette.jsonl",
            }
        ),
        encoding="utf-8",
    )
    originals = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
    out = tmp_path / "out"
    out.mkdir()
    prepared, _ = capture.prepare_suite(repo, out)
    copied = yaml.safe_load((prepared / "suite.yaml").read_text(encoding="utf-8"))
    case = yaml.safe_load((prepared / "cases/c21.yaml").read_text(encoding="utf-8"))
    assert copied["budgets"] == suite["budgets"]
    assert json.loads((prepared / copied["assertions"][0]["schema_path"]).read_text())[
        "required"
    ] == ["reply"]
    assert case["assertions"] == [{"type": "must_call", "tools": ["search_schema"]}]
    assert "baseline_path" not in copied and "regression" not in copied
    assert {path: path.read_bytes() for path in originals} == originals


def test_runtime_source_fingerprint_normalizes_line_endings_and_detects_changes(tmp_path):
    module = tmp_path / "__init__.py"
    module.write_bytes(b"VERSION = 'test'\r\n")
    first = capture.package_source_provenance(module)
    module.write_bytes(b"VERSION = 'test'\n")
    assert capture.package_source_provenance(module) == first
    (tmp_path / "changed.py").write_bytes(b"VALUE = 1\n")
    changed = capture.package_source_provenance(module)
    assert changed["python_files"] == 2
    assert changed["source_sha256"] != first["source_sha256"]
