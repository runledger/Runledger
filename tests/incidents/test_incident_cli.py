from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from runledger.incidents.cli import main


@pytest.fixture
def source(tmp_path: Path) -> Path:
    raw = {
        "schema_version": 1,
        "metadata": {"source": "private-metadata-never-exported"},
        "input": {"order_id": "private-order-3198", "request": "private-customer-message",
                  "password": "private-password-value", "rendering_probe": "<script>alert('sample')</script>"},
        "events": [
            {"type": "tool_call", "call_id": "private-original-call", "name": "issue_refund",
             "args": {"order_id": "private-order-3198"}},
            {"type": "business_effect", "call_id": "private-original-call",
             "effect": {"type": "refund", "order_id": "private-order-3198"}},
            {"type": "tool_result", "call_id": "private-original-call", "ok": True, "result": {}},
            {"type": "final_output", "output": {"status": "complete"}},
        ],
        "assertions": [{"id": "no-refunds", "type": "effect_count", "effect_type": "refund", "max": 0}],
        "effects_complete": True,
    }
    path = tmp_path / "private-source-filename.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def exported_text(directory: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in directory.iterdir() if path.is_file())


def test_import_artifacts_are_sanitized_and_html_escaped(source, tmp_path, capsys):
    directory = tmp_path / "imported"
    assert main(["import", str(source), "--out", str(directory)]) == 0
    assert {path.name for path in directory.iterdir()} == {
        "incident.json", "redaction-report.json", "evaluation.json", "trace.jsonl", "junit.xml", "report.html"}
    captured = capsys.readouterr()
    text = exported_text(directory) + captured.out + captured.err
    for value in ("private-metadata", "private-order", "private-customer-message", "private-password", "private-original-call", "private-source-filename"):
        assert value not in text
    report = (directory / "report.html").read_text(encoding="utf-8")
    assert "<script>" not in report
    assert "&lt;script&gt;" in report
    assert "Review required before sharing" in report
    assert ET.parse(directory / "junit.xml").getroot().attrib["failures"] == "1"


def test_inspect_gate_fails_on_recorded_business_violation(source, tmp_path):
    imported = tmp_path / "imported"
    assert main(["import", str(source), "--out", str(imported)]) == 0
    bundle = imported / "incident.json"
    assert main(["inspect", str(bundle), "--out", str(tmp_path / "view")]) == 0
    assert main(["inspect", str(bundle), "--out", str(tmp_path / "gate"), "--gate"]) == 1


def test_promote_never_overwrites_an_existing_fixture(source, tmp_path, capsys):
    imported = tmp_path / "imported"
    assert main(["import", str(source), "--out", str(imported)]) == 0
    target = tmp_path / "fixtures" / "regression.json"
    bundle = imported / "incident.json"
    assert main(["promote", str(bundle), "--to", str(target)]) == 0
    content = target.read_bytes()
    assert main(["promote", str(bundle), "--to", str(target)]) == 2
    assert target.read_bytes() == content
    assert "Existing evidence was not overwritten" in capsys.readouterr().err


def test_output_directory_cannot_overwrite_source_or_prior_evidence(source, tmp_path):
    source_bytes = source.read_bytes()
    assert main(["import", str(source), "--out", str(tmp_path)]) == 2
    assert source.read_bytes() == source_bytes
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("extra", [["--effects-complete"], ["--case", "private-case-value"],
                                    ["--redact", "/input/private-missing-path"]])
def test_invalid_import_options_create_no_artifacts(source, tmp_path, capsys, extra):
    directory = tmp_path / "failed"
    assert main(["import", str(source), "--out", str(directory), *extra]) == 2
    assert not directory.exists()
    output = capsys.readouterr()
    assert "private-" not in output.err
    assert "private-" not in output.out


def test_invalid_source_diagnostic_does_not_echo_private_values(tmp_path, capsys):
    source = tmp_path / "private-input-name.json"
    source.write_text('{"private-customer-token": "private-password", "broken":', encoding="utf-8")
    assert main(["import", str(source), "--out", str(tmp_path / "failed")]) == 2
    output = capsys.readouterr()
    assert "private-" not in output.err + output.out
    assert "valid bounded JSON" in output.err


def test_malformed_agent_command_is_not_echoed_or_executed(source, tmp_path, capsys):
    imported = tmp_path / "imported"
    assert main(["import", str(source), "--out", str(imported)]) == 0
    capsys.readouterr()
    destination = tmp_path / "replayed"
    assert main(["replay", str(imported / "incident.json"), "--out", str(destination),
                 "--agent-command", "private-command-secret-invalid-json"]) == 2
    assert not destination.exists()
    output = capsys.readouterr()
    assert "private-command" not in output.err + output.out


def adapter(tmp_path: Path, *, private_output: bool = False) -> str:
    path = tmp_path / "adapter.py"
    path.write_text('''import json
import sys

start = json.loads(sys.stdin.readline())
print(json.dumps({"type": "tool_call", "call_id": "adapter-call", "name": "issue_refund",
                  "args": {"order_id": start["input"]["order_id"]}}), flush=True)
json.loads(sys.stdin.readline())
print(json.dumps({"type": "final_output", "output": {"status": STATUS}}), flush=True)
'''.replace("STATUS", repr("private-unexpected-agent-secret" if private_output else "complete")), encoding="utf-8")
    return json.dumps([sys.executable, str(path)])


@pytest.mark.parametrize("gate,expected", [(False, 0), (True, 1)])
def test_replay_matching_failure_needs_gate_for_business_exit_status(source, tmp_path, gate, expected):
    imported = tmp_path / "imported"
    assert main(["import", str(source), "--out", str(imported)]) == 0
    destination = tmp_path / "replayed"
    argv = ["replay", str(imported / "incident.json"), "--out", str(destination),
            "--agent-command", adapter(tmp_path)]
    assert main(argv + (["--gate"] if gate else [])) == expected
    replay = json.loads((destination / "replay.json").read_text(encoding="utf-8"))
    assert replay["matched"] is True
    assert replay["observed"]["passed"] is False
    assert ET.parse(destination / "junit.xml").getroot().attrib["failures"] == "1"


def test_unmatched_candidate_secret_never_reaches_any_exported_artifact(source, tmp_path, capsys):
    imported = tmp_path / "imported"
    assert main(["import", str(source), "--out", str(imported)]) == 0
    destination = tmp_path / "replayed"
    assert main(["replay", str(imported / "incident.json"), "--out", str(destination),
                 "--agent-command", adapter(tmp_path, private_output=True)]) == 1
    output = capsys.readouterr()
    assert "private-unexpected-agent-secret" not in exported_text(destination) + output.out + output.err
    replay = json.loads((destination / "replay.json").read_text(encoding="utf-8"))
    assert replay["matched"] is False
