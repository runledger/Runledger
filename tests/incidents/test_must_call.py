"""A schema-correct answer cannot hide a skipped required tool."""
import json

import pytest

from runledger.incidents.cli import main
from runledger.incidents.replay import evaluate_incident
from runledger.incidents.schema import IncidentError, validate_rules

RULE = {"id": "schema-discovery", "type": "must_call", "tools": ["search_schema"]}


def incident(called=(), *, task_error=False):
    events = []
    for number, name in enumerate(called, 1):
        events.extend([
            {"type": "tool_call", "call_id": f"c{number}", "name": name, "args": {}},
            {"type": "tool_result", "call_id": f"c{number}", "ok": False,
             "result": None, "error": "provider_timeout"},
        ])
    events.append({"type": "task_error", "message": "failed"} if task_error else
                  {"type": "final_output", "output": {"sql": "SELECT 1"}})
    return {"id": "schema-discovery", "input": {}, "events": events,
            "assertions": [RULE], "effects_complete": False}


def test_missing_tool_fails_despite_valid_output_and_unrelated_calls():
    result = evaluate_incident(incident(["execute_sql"]))
    assert not result["passed"]
    assert result["assertions"][0]["actual"] == {"missing": ["search_schema"]}
    assert result["assertions"][0]["status"] == "fail"


def test_required_call_does_not_claim_success_and_task_error_still_fails():
    assert evaluate_incident(incident(["search_schema"]))["passed"]
    assert not evaluate_incident(incident(["search_schema"], task_error=True))["passed"]


@pytest.mark.parametrize("names", [[], "search_schema", [None], [True], [{}],
                                  ["search_schema"] * 2, ["bad name"],
                                  [f"tool{i}" for i in range(31)]])
def test_required_tools_are_bounded_unique_identifiers(names):
    with pytest.raises(IncidentError):
        validate_rules([{**RULE, "tools": names}])


@pytest.mark.parametrize("called,expected", [([], 1), (["search_schema"], 0)])
def test_import_redaction_and_gate_preserve_same_rule(tmp_path, called, expected):
    data = incident(called)
    source = tmp_path / "source.json"
    data.pop("id")
    source.write_text(json.dumps({"schema_version": 1, **data}), encoding="utf-8")
    imported = tmp_path / "imported"
    assert main(["import", str(source), "--out", str(imported)]) == 0
    bundle = imported / "incident.json"
    assert json.loads(bundle.read_text())["incident"]["assertions"] == [RULE]
    assert main(["inspect", str(bundle), "--gate", "--out", str(tmp_path / "gate")]) == expected
