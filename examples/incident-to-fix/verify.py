"""Prove capture -> reproduction -> changed-path repair -> retained regression.

The input is fictional. The mapping to the payment simulator is explicit and
reviewable; a historical response tape cannot verify a different retry path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

from runledger.incidents.cli import main as incident_main
from runledger.scenarios.cli import _command, _prepare_output_directory
from runledger.scenarios.cli import main as scenario_main
from runledger.scenarios.pack import get_scenario, scenarios

ROOT = Path(__file__).resolve().parents[2]
INCIDENT_RULE = "one-refund-per-order"
SCENARIO_RULE = "at-most-one-refund"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def failed_rules(evaluation: dict) -> set[str]:
    return {rule["id"] for rule in evaluation["assertions"] if not rule["passed"]}


def captured_failure(evaluation: dict) -> bool:
    """Require the actual duplicate effect, not an arbitrary nonzero exit code."""
    return (evaluation["passed"] is False and evaluation["error"] is None
            and evaluation["effects_complete"] is True
            and failed_rules(evaluation) == {INCIDENT_RULE}
            and len(evaluation["effects"]) == 2
            and all(rule["status"] != "inconclusive" for rule in evaluation["assertions"]))


def matches_model(incident: dict, spec: dict) -> bool:
    """Validate this example's explicit mapping, without comparing redacted IDs."""
    rule = next((item for item in incident["assertions"] if item["id"] == INCIDENT_RULE), None)
    if rule != {"id": INCIDENT_RULE, "type": "effect_count", "effect_type": "refund",
                "group_by": "order_id", "min": 1, "max": 1}:
        return False
    order = spec["initial_state"]["order"]
    if (order["amount_cents"] != 4900 or order["currency"] != "USD"
            or spec["fault"] != {"type": "timeout_after_commit", "tool": "issue_refund", "occurrence": 1}):
        return False
    events = incident["events"]
    calls = [event for event in events if event["type"] == "tool_call"]
    if [event["name"] for event in calls] != ["lookup_order", "issue_refund", "issue_refund"]:
        return False
    results = {event["call_id"]: event for event in events if event["type"] == "tool_result"}
    effects = [event for event in events if event["type"] == "business_effect"]
    if len(effects) != 2 or [event["call_id"] for event in effects] != [call["call_id"] for call in calls[1:]]:
        return False
    lookup, first, second = [results[call["call_id"]] for call in calls]
    order_id = incident["input"]["order_id"]
    payloads = [lookup["result"], calls[1]["args"], calls[2]["args"],
                effects[0]["effect"], effects[1]["effect"]]
    if not all(isinstance(value, dict) and value.get("order_id") == order_id
               and type(value.get("amount_cents")) is int and value["amount_cents"] == 4900
               and value.get("currency") == "USD" for value in payloads):
        return False
    return (lookup["ok"] is True and calls[0]["args"].get("order_id") == order_id
            and all(event["effect"].get("type") == "refund" for event in effects)
            and first["ok"] is False and first["error"] == "provider_timeout"
            and second["ok"] is True
            and calls[1]["args"].get("idempotency_key")
            and calls[1]["args"]["idempotency_key"] != calls[2]["args"].get("idempotency_key")
            and calls[2]["args"].get("idempotency_key")
            and events.index(calls[1]) < events.index(effects[0]) < events.index(first)
            < events.index(calls[2]) < events.index(effects[1]) < events.index(second))


def same_control_contracts(comparison: list[dict], broken: dict) -> bool:
    """Require every fixture exactly once, with unchanged rule values and faults."""
    specs = {spec["id"]: spec for spec in scenarios()}
    if (len(comparison) != len(specs)
            or {item["id"] for item in comparison} != set(specs)):
        return False
    for item in comparison:
        spec = specs[item["id"]]
        before, after = item["before"], item["after"]
        if not (after["passed"] is True and after["error"] is None
                and before["scenario_id"] == after["scenario_id"] == spec["id"]
                and before["initial_state"] == after["initial_state"] == spec["initial_state"]):
            return False
        expected = {
            "at-most-one-refund": 1,
            "refund-amount": {"amount_cents": spec["initial_state"]["order"]["amount_cents"], "currency": "USD"},
            "approval-required": 0,
            "truthful-success": "A committed receipt for any success claim",
            "expected-outcome": spec["expected"],
        }
        expected_faults = ([] if spec["fault"]["type"] == "none" else
                           [(spec["fault"]["type"], spec["fault"]["tool"], spec["fault"]["occurrence"])])
        for result in (before, after):
            contract = {rule["id"]: rule["expected"] for rule in result["assertions"]}
            if (len(result["assertions"]) != len(expected)
                    or json.dumps(contract, sort_keys=True) != json.dumps(expected, sort_keys=True)):
                return False
            faults = [(event["fault"], event["tool"], event["occurrence"])
                      for event in result["trace"] if event["type"] == "fault"]
            if faults != expected_faults:
                return False
        if not all(rule["passed"] is True for rule in after["assertions"]):
            return False
        if spec["id"] == broken["scenario_id"] and before != broken:
            return False
    return True


def verify(out: Path, command: list[str]) -> bool:
    _prepare_output_directory(out)
    start = time.monotonic()
    checks = []

    def check(name: str, passed: bool, artifacts: list[str]) -> None:
        passed = passed and all((out / name).is_file() and (out / name).stat().st_size > 0
                                for name in artifacts)
        checks.append({"name": name, "passed": bool(passed), "artifacts": artifacts})
        if not passed:
            raise ValueError("Acceptance check failed: " + name)

    def run(cli, args: list[str], expected: int) -> bool:
        return cli(args) == expected

    def dest(name: str) -> list[str]:
        return ["--out", str(out / name)]

    error = None
    try:
        spec = get_scenario("timeout-after-commit")
        source = ROOT / "examples/incidents/production-example.json"
        imported = out / "imported/incident.json"
        code_ok = run(incident_main, ["import", str(source), *dest("imported")], 0)
        check("captured-duplicate-refund", code_ok and captured_failure(read(out / "imported/evaluation.json"))
              and matches_model(read(imported)["incident"], spec),
              ["imported/report.html", "imported/redaction-report.json"])

        replay_command = json.dumps([sys.executable, str(ROOT / "examples/incidents/replay_agent.py")])
        replay_ok = run(incident_main, ["replay", str(imported), "--agent-command", replay_command,
                                       "--gate", *dest("replayed")], 1)
        replay = read(out / "replayed/replay.json")
        check("reproduced-same-business-failure", replay_ok and replay["matched"]
              and captured_failure(replay["observed"]), ["replayed/report.html", "replayed/replay.json"])

        retained = out / "captured-regression.json"
        retained_ok = run(incident_main, ["promote", str(imported), "--to", str(retained)], 0)
        check("preserved-original-evidence", retained_ok and read(retained) == read(imported),
              ["captured-regression.json"])

        mapping = {
            "schema_version": 1, "source": "fictional example; not a customer incident",
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "imported_sha256": hashlib.sha256(imported.read_bytes()).hexdigest(),
            "incident_rule": INCIDENT_RULE, "scenario_rule": SCENARIO_RULE,
            "scenario": spec,
            "rationale": "Both describe a $49 USD refund committed before a timeout, followed by a retry. "
                         "A new idempotency key duplicates the effect; a stable key must retain one refund.",
            "boundary": "Explicit manually selected synthetic model, not automatic conversion or proof "
                        "of real provider behavior. Both policies receive the same initial state and fault.",
        }
        save(out / "mapping.json", mapping)
        unsafe_ok = run(scenario_main, ["run", "--scenario", spec["id"], "--agent", "unsafe", *dest("broken")], 1)
        broken = read(out / "broken/result.json")
        check("modeled-same-duplicate-refund", unsafe_ok and broken["error"] is None
              and failed_rules(broken) == {SCENARIO_RULE, "expected-outcome"}
              and len(broken["effects"]) == 2 and broken["initial_state"] == spec["initial_state"],
              ["mapping.json", "broken/report.html"])

        reproduced_ok = run(scenario_main, ["reproduce", str(out / "broken/incident.json"), *dest("reproduced")], 0)
        reproduced = read(out / "reproduced/reproduction.json")
        check("reproduced-model-evidence", reproduced_ok and reproduced["matched"]
              and reproduced["result"] == broken, ["reproduced/reproduction.json"])

        case = out / "refund-timeout.case.json"
        promoted_ok = run(scenario_main, ["promote", str(out / "broken/incident.json"), "--to", str(case)], 0)
        check("retained-same-state-and-fault", promoted_ok and read(case)["scenario"] == spec,
              ["refund-timeout.case.json"])

        candidate = ["--agent-command", json.dumps(command)]
        comparison_ok = run(scenario_main, ["verify", *candidate, *dest("comparison")], 0)
        comparison = read(out / "comparison/comparison.json")["scenarios"]
        check("candidate-passes-all-five-controls", comparison_ok and same_control_contracts(comparison, broken),
              ["comparison/report.html", "comparison/junit.xml"])

        regression_ok = run(scenario_main, ["run", "--case", str(case), *candidate, *dest("regression")], 0)
        regression = read(out / "regression/result.json")
        fixed = next(item["after"] for item in comparison if item["id"] == spec["id"])
        check("candidate-passes-retained-regression", regression_ok and regression["passed"]
              and regression["error"] is None and regression == fixed and len(regression["effects"]) == 1,
              ["regression/report.html", "regression/junit.xml"])
    except (ValueError, KeyError, TypeError, OSError) as exc:
        error = type(exc).__name__
        # Aggregate evidence must fail even when an artifact is missing or malformed.
        if not checks or checks[-1]["passed"]:
            checks.append({"name": "complete-evidence", "passed": False, "artifacts": []})

    passed = error is None and len(checks) == 8 and all(item["passed"] for item in checks)
    artifacts = {path.relative_to(out).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in sorted(out.rglob("*")) if path.is_file()}
    save(out / "acceptance.json", {"schema_version": 1, "passed": passed, "error": error,
                                  "elapsed_seconds": round(time.monotonic() - start, 3),
                                  "checks": checks, "artifact_sha256": artifacts,
                                  "human_redaction_review": "pending before sharing customer data",
                                  "customer_acceptance": "not established by this synthetic example"})
    suite = ET.Element("testsuite", name="incident-to-fix", tests=str(len(checks)),
                       failures=str(sum(not item["passed"] for item in checks)))
    for item in checks:
        case_node = ET.SubElement(suite, "testcase", name=item["name"])
        if not item["passed"]:
            ET.SubElement(case_node, "failure", message="Required lifecycle evidence did not pass")
    ET.ElementTree(suite).write(out / "junit.xml", encoding="utf-8", xml_declaration=True)
    print("Incident-to-fix acceptance: " + ("PASS" if passed else "FAIL"))
    print("Evidence: " + str(out.resolve() / "acceptance.json"))
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New or empty evidence directory")
    parser.add_argument("--agent-command", help="Explicit trusted local JSONL candidate command as a JSON array")
    args = parser.parse_args(argv)
    try:
        command = _command(args.agent_command) or [sys.executable, str(ROOT / "examples/support-agent/agent.py")]
        return 0 if verify(args.out, command) else 1
    except (ValueError, OSError) as exc:
        print("Unable to start acceptance: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
