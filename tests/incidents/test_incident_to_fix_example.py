import copy
import importlib.util
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/incident-to-fix/verify.py"
spec = importlib.util.spec_from_file_location("incident_to_fix_example", EXAMPLE)
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


def test_complete_lifecycle_and_nonoverwriting_evidence(tmp_path):
    out = tmp_path / "evidence"
    assert example.main(["--out", str(out)]) == 0
    result = json.loads((out / "acceptance.json").read_text())
    assert result["passed"] and len(result["checks"]) == 8
    assert result["artifact_sha256"]["regression/result.json"]
    assert ET.parse(out / "junit.xml").getroot().attrib["failures"] == "0"
    original = (out / "acceptance.json").read_bytes()
    assert example.main(["--out", str(out)]) == 2
    assert (out / "acceptance.json").read_bytes() == original


@pytest.mark.parametrize("behavior", ["noop", "crash", "unsafe"])
def test_invalid_candidates_cannot_pass_acceptance(tmp_path, behavior):
    adapter = tmp_path / "candidate.py"
    if behavior == "noop":
        source = 'import json\nprint(json.dumps({"type":"final_output","output":{"status":"refunded"}}), flush=True)\n'
    elif behavior == "crash":
        source = "raise SystemExit(3)\n"
    else:
        source = (example.ROOT / "examples/support-agent/agent.py").read_text().replace(
            'run_policy("fixed",', 'run_policy("unsafe",')
    adapter.write_text(source, encoding="utf-8")
    out = tmp_path / "evidence"
    assert example.main(["--out", str(out), "--agent-command", json.dumps([sys.executable, str(adapter)])]) == 1
    result = json.loads((out / "acceptance.json").read_text())
    assert not result["passed"]
    assert result["checks"][-1]["name"] == "candidate-passes-all-five-controls"
    assert ET.parse(out / "junit.xml").getroot().attrib["failures"] == "1"


def test_missing_evidence_fails_aggregate_even_when_subcommand_exits_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(example, "incident_main", lambda args: 0)
    assert example.main(["--out", str(tmp_path / "evidence")]) == 1
    result = example.read(tmp_path / "evidence/acceptance.json")
    assert not result["passed"]
    assert result["checks"] == [{"name": "complete-evidence", "passed": False, "artifacts": []}]


@pytest.mark.parametrize("change", ["incomplete", "wrong_failure", "crash"])
def test_expected_failure_requires_complete_specific_business_evidence(change):
    data = {"passed": False, "error": None, "effects_complete": True,
            "assertions": [{"id": example.INCIDENT_RULE, "passed": False, "status": "fail"}],
            "effects": [{}, {}]}
    assert example.captured_failure(data)
    if change == "incomplete":
        data["effects_complete"] = False
    elif change == "wrong_failure":
        data["assertions"][0]["id"] = "unrelated-failure"
    else:
        data["error"] = "adapter_crashed"
    assert not example.captured_failure(data)


@pytest.mark.parametrize("change", ["missing-report", "duplicate-control", "weakened-rule", "changed-fault"])
def test_corrupted_comparison_cannot_claim_complete_fix(tmp_path, monkeypatch, change):
    original = example.scenario_main

    def corrupt(args):
        code = original(args)
        if args[0] == "verify":
            directory = Path(args[args.index("--out") + 1])
            path = directory / "comparison.json"
            data = example.read(path)
            if change == "missing-report":
                (directory / "report.html").unlink()
            elif change == "duplicate-control":
                data["scenarios"][0] = copy.deepcopy(data["scenarios"][1])
            elif change == "weakened-rule":
                data["scenarios"][0]["after"]["assertions"][0]["expected"] = 2
            else:
                fault = next(event for event in data["scenarios"][1]["after"]["trace"]
                             if event["type"] == "fault")
                fault["fault"] = "none"
            example.save(path, data)
        return code

    monkeypatch.setattr(example, "scenario_main", corrupt)
    out = tmp_path / "evidence"
    assert example.main(["--out", str(out)]) == 1
    result = example.read(out / "acceptance.json")
    assert not result["passed"]
    assert result["checks"][-1]["name"] == "candidate-passes-all-five-controls"
    assert ET.parse(out / "junit.xml").getroot().get("failures") == "1"


@pytest.mark.parametrize("change", ["amount", "currency", "weakened-rule", "same-retry-key", "late-effect"])
def test_mapping_rejects_different_incident_conditions(change):
    incident = example.read(example.ROOT / "examples/incidents/production-example.json")
    spec = example.get_scenario("timeout-after-commit")
    assert example.matches_model(incident, spec)
    if change in {"amount", "currency"}:
        for event in incident["events"]:
            for field in ("args", "result", "effect"):
                value = event.get(field)
                if isinstance(value, dict) and "amount_cents" in value:
                    value["amount_cents" if change == "amount" else "currency"] = (
                        5000 if change == "amount" else "EUR"
                    )
    elif change == "weakened-rule":
        incident["assertions"][0]["max"] = 2
    elif change == "same-retry-key":
        incident["events"][5]["args"]["idempotency_key"] = incident["events"][2]["args"]["idempotency_key"]
    else:
        incident["events"][3], incident["events"][4] = incident["events"][4], incident["events"][3]
    assert not example.matches_model(incident, spec)
