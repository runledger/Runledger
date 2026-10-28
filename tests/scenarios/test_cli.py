from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path

import pytest

from runledger.scenarios.cli import main
from runledger.scenarios.core import run_scenario
from runledger.scenarios.pack import get_scenario
from runledger.scenarios.reports import compare_runs, write_report


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_installed_cli_bridge_verifies_all_cases_and_writes_evidence(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "verified"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "runledger", "scenario", "verify", "--out", str(output)],
        cwd=root, env=environment, capture_output=True, text=True, timeout=30, check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    comparison = _read(output / "comparison.json")
    assert len(comparison["scenarios"]) == 5
    assert all(item["comparison"]["verified"] for item in comparison["scenarios"])
    duplicate = next(item for item in comparison["scenarios"] if item["id"] == "timeout-after-commit")
    assert duplicate["comparison"]["before_refunds"] == 2
    assert duplicate["comparison"]["after_refunds"] == 1
    assert duplicate["comparison"]["repaired"] is True
    assert (output / "report.html").is_file()
    assert ET.parse(output / "junit.xml").getroot().attrib["failures"] == "0"
    assert (output / "timeout-after-commit" / "before" / "incident.json").is_file()
    assert (output / "timeout-after-commit" / "after" / "incident.json").is_file()


def test_failure_reproduce_promote_and_fixed_regression_end_to_end(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    assert main(["run", "--scenario", "timeout-after-commit", "--agent", "unsafe", "--out", str(broken)]) == 1
    failed = _read(broken / "result.json")
    assert failed["passed"] is False
    assert len(failed["effects"]) == 2
    assert ET.parse(broken / "junit.xml").getroot().attrib["failures"] == "1"
    incident = broken / "incident.json"
    reproduced = tmp_path / "reproduced"
    assert main(["reproduce", str(incident), "--out", str(reproduced)]) == 0
    reproduction = _read(reproduced / "reproduction.json")
    assert reproduction["matched"] is True
    assert reproduction["result"]["passed"] is False
    case = tmp_path / "cases" / "refund-regression.json"
    assert main(["promote", str(incident), "--to", str(case)]) == 0
    original = case.read_bytes()
    assert main(["promote", str(incident), "--to", str(case)]) == 2
    assert case.read_bytes() == original
    fixed = tmp_path / "regression"
    assert main(["run", "--case", str(case), "--agent", "fixed", "--out", str(fixed)]) == 0
    assert _read(fixed / "result.json")["passed"] is True


def test_nonempty_output_is_preserved_before_custom_program_is_executed(tmp_path: Path) -> None:
    output = tmp_path / "previous"
    assert main(["run", "--scenario", "happy-path", "--out", str(output)]) == 0
    original = {file.name: file.read_bytes() for file in output.iterdir()}
    sentinel = tmp_path / "executed.txt"
    command = [sys.executable, "-c", f"from pathlib import Path; Path({str(sentinel)!r}).write_text('ran')"]
    assert main(["run", "--scenario", "happy-path", "--agent-command", json.dumps(command), "--out", str(output)]) == 2
    assert not sentinel.exists()
    assert {file.name: file.read_bytes() for file in output.iterdir()} == original
    assert main(["verify", "--out", str(output)]) == 2
    assert main(["reproduce", str(output / "incident.json"), "--out", str(output)]) == 2
    assert {file.name: file.read_bytes() for file in output.iterdir()} == original


def test_custom_agent_runs_against_simulator_without_exporting_its_trace(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTHONPATH", str(root / "src"))
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import json, sys\n"
        "from runledger.scenarios.agents import run_policy\n"
        "def send(value):\n"
        "    print(json.dumps(value), flush=True)\n"
        "count = 0\n"
        "def call(name, args):\n"
        "    global count\n"
        "    count += 1\n"
        "    send({'type':'tool_call', 'name':name, 'args':args, 'call_id':str(count)})\n"
        "    return json.loads(sys.stdin.readline())\n"
        "request = json.loads(sys.stdin.readline())\n"
        "send({'type':'log','level':'info','message':'private-customer@example.test'})\n"
        "result = run_policy('fixed', call, request['input'])\n"
        "send({'type':'final_output','output':result})\n",
        encoding="utf-8",
    )
    output = tmp_path / "custom"
    command = json.dumps([sys.executable, str(adapter)])
    assert main(["verify", "--scenario", "timeout-after-commit", "--agent-command", command, "--out", str(output)]) == 0
    before = output / "timeout-after-commit" / "before"
    after = output / "timeout-after-commit" / "after"
    assert (before / "incident.json").is_file()
    assert not (after / "incident.json").exists()
    assert _read(after / "result.json")["agent"] == "custom"
    assert "private-customer@example.test" in (after / "trace.jsonl").read_text(encoding="utf-8")


@pytest.mark.parametrize("mutation", ["outer-version", "inner-integer"])
def test_promoted_case_rejects_boolean_for_integer_substitution(tmp_path: Path, mutation: str) -> None:
    case = {"schema_version": 1, "scenario": get_scenario("happy-path")}
    if mutation == "outer-version":
        case["schema_version"] = True
    else:
        case["scenario"]["schema_version"] = True
    path = tmp_path / "case.json"
    path.write_text(json.dumps(case), encoding="utf-8")
    output = tmp_path / "bad"
    assert main(["run", "--case", str(path), "--out", str(output)]) == 2
    assert not output.exists()


def test_report_escapes_custom_agent_values_without_executable_markup(tmp_path: Path) -> None:
    run = run_scenario(get_scenario("happy-path"), agent="fixed")
    attack = '</pre><script>alert("x")</script><img src=x onerror=alert(1)>'
    run["agent"] = attack
    run["title"] = attack
    run["output"]["message"] = attack
    run["error"] = {"message": attack}
    run["assertions"][0]["label"] = attack
    run["trace"].append({"step": 99, "type": attack, "name": attack, "data": attack})
    path = tmp_path / "report.html"
    write_report(path, runs=[run])
    text = path.read_text(encoding="utf-8")
    assert "&lt;script&gt;" in text
    assert attack not in text

    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []

        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)

    parsed = Tags()
    parsed.feed(text)
    assert "script" not in parsed.tags
    assert "img" not in parsed.tags


def test_first_divergence_ignores_call_ids_and_trace_steps() -> None:
    before = run_scenario(get_scenario("timeout-after-commit"), agent="unsafe")
    after = deepcopy(before)
    actions = [event for event in after["trace"] if event["type"] == "tool_call"]
    for index, action in enumerate(actions):
        action["step"] = 100 + index
        action["call_id"] = f"different-{index}"
    assert compare_runs(before, after)["first_divergence"] is None
    actions[-1]["args"]["idempotency_key"] = "stable-key"
    divergence = compare_runs(before, after)["first_divergence"]
    original_actions = [event for event in before["trace"] if event["type"] == "tool_call"]
    assert divergence["step"] == original_actions[-1]["step"]
    assert divergence["action_index"] == len(actions)
    assert divergence["before_step"] == original_actions[-1]["step"]
    assert divergence["after_step"] == actions[-1]["step"]
    assert divergence["after"]["args"]["idempotency_key"] == "stable-key"


def test_divergence_detects_missing_action_and_final_output() -> None:
    before = run_scenario(get_scenario("happy-path"), agent="fixed")
    after = deepcopy(before)
    after["output"]["message"] = "Changed final reply"
    final_after = next(event for event in after["trace"] if event["type"] == "final_output")
    final_after["output"] = after["output"]
    divergence = compare_runs(before, after)["first_divergence"]
    assert divergence["after"] == final_after
    assert divergence["step"] == final_after["step"]
    after = deepcopy(before)
    last = next(event for event in reversed(after["trace"]) if event["type"] == "tool_call")
    after["trace"].remove(last)
    assert compare_runs(before, after)["first_divergence"]["after"] is None


def test_comparison_refuses_different_scenario_or_world() -> None:
    before = run_scenario(get_scenario("happy-path"), agent="unsafe")
    with pytest.raises(ValueError, match="same scenario"):
        compare_runs(before, run_scenario(get_scenario("timeout-after-commit"), agent="fixed"))
    after = deepcopy(before)
    after["initial_state"]["order"]["amount_cents"] += 1
    with pytest.raises(ValueError, match="same initial state"):
        compare_runs(before, after)
