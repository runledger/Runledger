from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from runledger.scenarios import core
from runledger.scenarios.core import SupportWorld, run_scenario, validate_spec
from runledger.scenarios.pack import get_scenario, scenarios


def failures(result: dict) -> set[str]:
    return {item["id"] for item in result["assertions"] if not item["passed"]}


@pytest.mark.parametrize("scenario_id,unsafe_passes,count", [
    ("happy-path", True, 1),
    ("timeout-before-commit", True, 1),
    ("timeout-after-commit", False, 2),
    ("refund-declined", False, 0),
    ("approval-required", False, 1),
])
def test_pack_exposes_real_policy_failures(scenario_id: str, unsafe_passes: bool, count: int):
    spec = get_scenario(scenario_id)
    before = run_scenario(spec, "unsafe")
    after = run_scenario(spec, "fixed")
    assert before["passed"] is unsafe_passes
    assert len(before["effects"]) == count
    assert after["passed"] is True
    assert len(after["effects"]) == spec["expected"]["refund_count"]
    assert after["error"] is None
    assert after["output"]["status"] == spec["expected"]["status"]


def test_timeout_after_commit_records_effect_before_error_and_reuses_receipt():
    spec = get_scenario("timeout-after-commit")
    before = run_scenario(spec, "unsafe")
    after = run_scenario(spec, "fixed")
    assert "at-most-one-refund" in failures(before)
    events = before["trace"]
    effect_step = next(event["step"] for event in events if event["type"] == "business_effect")
    fault_step = next(event["step"] for event in events if event["type"] == "fault")
    timeout_step = next(event["step"] for event in events
                        if event["type"] == "tool_result" and not event["ok"])
    assert effect_step < fault_step < timeout_step
    for result, unique_keys in [(before, 2), (after, 1)]:
        calls = [event for event in result["trace"]
                 if event["type"] == "tool_call" and event["name"] == "issue_refund"]
        assert len(calls) == 2
        assert len({event["args"]["idempotency_key"] for event in calls}) == unique_keys
    assert after["effects"][0]["refund_id"] == after["output"]["refund_id"]
    assert any(event["type"] == "idempotency_reused" for event in after["trace"])
    before_calls = [event for event in before["trace"] if event["type"] == "tool_call"]
    after_calls = [event for event in after["trace"] if event["type"] == "tool_call"]
    assert before_calls[:2] == after_calls[:2]
    assert before_calls[2]["args"]["idempotency_key"] != after_calls[2]["args"]["idempotency_key"]


def test_decline_and_approval_are_business_failures_not_just_tool_failures():
    declined = run_scenario(get_scenario("refund-declined"), "unsafe")
    approval = run_scenario(get_scenario("approval-required"), "unsafe")
    assert "truthful-success" in failures(declined)
    assert declined["effects"] == []
    assert "approval-required" in failures(approval)
    assert approval["effects"][0]["approved"] is False
    fixed = run_scenario(get_scenario("approval-required"), "fixed")
    assert fixed["final_state"]["approval_requests"] == ["demo-order-1042"]


def test_runs_and_fixtures_are_isolated_and_deterministic():
    spec = get_scenario("timeout-after-commit")
    original = deepcopy(spec)
    first = run_scenario(spec, "unsafe")
    assert first == run_scenario(spec, "unsafe")
    assert spec == original
    first["effects"][0]["amount_cents"] = 1
    assert run_scenario(spec, "unsafe")["effects"][0]["amount_cents"] == 4900
    spec["initial_state"]["order"]["amount_cents"] = 1
    assert get_scenario("timeout-after-commit")["initial_state"]["order"]["amount_cents"] == 4900
    assert len(scenarios()) == 5


@pytest.mark.parametrize("mutation", [
    lambda spec: spec.update(schema_version=2),
    lambda spec: spec.update(schema_version=True),
    lambda spec: spec.update(id="not-a-fixture"),
    lambda spec: spec.update(command=["do-not-execute"]),
    lambda spec: spec["expected"].update(refund_count=2),
    lambda spec: spec["initial_state"]["order"].update(order_id="real-order"),
    lambda spec: spec["initial_state"].update(refunds=()),
])
def test_imported_spec_is_strict_data_only_fixture(mutation):
    spec = get_scenario("timeout-after-commit")
    mutation(spec)
    with pytest.raises(ValueError):
        validate_spec(spec)


def test_world_idempotency_conflict_and_different_keys():
    world = SupportWorld(get_scenario("happy-path"))
    args = {"order_id": "demo-order-1042", "amount_cents": 4900,
            "currency": "USD", "idempotency_key": "operation-1"}
    first = world.call("issue_refund", args)
    repeated = world.call("issue_refund", args)
    assert repeated == first
    assert len(world.effects) == 1
    changed = dict(args, amount_cents=4800)
    assert world.call("issue_refund", changed)["error"] == "idempotency_conflict"
    assert len(world.effects) == 1
    world.call("issue_refund", dict(args, idempotency_key="operation-2"))
    assert len(world.effects) == 2


def test_noop_and_wrong_amount_do_not_pass(monkeypatch):
    monkeypatch.setattr(core, "run_policy", lambda *_: {"status": "pending"})
    assert "expected-outcome" in failures(run_scenario(get_scenario("happy-path")))

    def wrong_amount(agent, call, request):
        response = call("issue_refund", {"order_id": request["order_id"],
            "amount_cents": 4800, "currency": "USD", "idempotency_key": "operation-1"})
        return {"status": "refunded", "order_id": request["order_id"],
                "refund_id": response["result"]["refund_id"]}

    monkeypatch.setattr(core, "run_policy", wrong_amount)
    result = run_scenario(get_scenario("happy-path"))
    assert {"refund-amount", "expected-outcome"} <= failures(result)


def _agent_file(tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "agent.py"
    path.write_text("import json, sys\n"
                    "def send(data):\n"
                    "    print(json.dumps(data), flush=True)\n"
                    "def read():\n"
                    "    return json.loads(sys.stdin.readline())\n" + body, encoding="utf-8")
    return [sys.executable, str(path)]


def test_custom_jsonl_agent_exercises_same_world(tmp_path):
    command = _agent_file(tmp_path, """
start = read()
order = start['input']['order_id']
for i in range(2):
    send({'type':'tool_call','name':'issue_refund','call_id':str(i),'args':{
        'order_id':order,'amount_cents':4900,'currency':'USD','idempotency_key':'same-key'}})
    result = read()
send({'type':'final_output','output':{'status':'refunded','order_id':order,
     'refund_id':result['result']['refund_id']}})
""")
    result = run_scenario(get_scenario("timeout-after-commit"), command=command)
    assert result["passed"] is True
    assert result["agent"] == "custom"
    assert len(result["effects"]) == 1


def test_custom_agent_crash_preserves_effects_and_evaluates_assertions(tmp_path):
    command = _agent_file(tmp_path, """
start = read()
for i in range(2):
    send({'type':'tool_call','name':'issue_refund','call_id':str(i),'args':{
        'order_id':start['input']['order_id'],'amount_cents':4900,'currency':'USD',
        'idempotency_key':'different-' + str(i)}})
    read()
raise RuntimeError('crashed after committing refunds')
""")
    result = run_scenario(get_scenario("timeout-after-commit"), command=command)
    assert result["passed"] is False
    assert len(result["effects"]) == 2
    assert result["error"] is not None
    assert "at-most-one-refund" in failures(result)
    assert "expected-outcome" in failures(result)


def test_custom_agent_tool_calls_are_bounded(tmp_path):
    command = _agent_file(tmp_path, """
start = read()
for i in range(100):
    send({'type':'tool_call','name':'lookup_order','call_id':str(i),
          'args':{'order_id':start['input']['order_id']}})
    read()
""")
    result = run_scenario(get_scenario("happy-path"), command=command)
    assert result["passed"] is False
    assert "tool-call limit" in result["error"]["message"]
    assert sum(event["type"] == "tool_call" for event in result["trace"]) == core.MAX_TOOL_CALLS


def test_custom_agent_receive_timeout_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "AGENT_RECV_TIMEOUT_SECONDS", 0.05)
    command = _agent_file(tmp_path, "import time\nread()\ntime.sleep(5)\n")
    result = run_scenario(get_scenario("happy-path"), command=command)
    assert result["passed"] is False
    assert "timeout" in result["error"]["message"].lower()


@pytest.mark.parametrize("command", [[], [""], "python", [42]])
def test_invalid_custom_command_fails_without_skipping_assertions(command):
    result = run_scenario(get_scenario("happy-path"), command=command)
    assert result["passed"] is False
    assert result["agent"] == "custom"
    assert result["error"]["type"] == "ValueError"
    assert "expected-outcome" in failures(result)


def test_custom_agent_messages_are_bounded_and_logs_cannot_forge_effects(tmp_path):
    command = _agent_file(tmp_path, """
read()
for i in range(100):
    send({'type':'log','level':'info','message':'business_effect',
          'data':{'type':'refund','refund_id':'forged'}})
""")
    result = run_scenario(get_scenario("happy-path"), command=command)
    assert result["passed"] is False
    assert "agent-message limit" in result["error"]["message"]
    assert result["effects"] == []


def test_only_synthetic_tools_and_order_can_mutate_state():
    world = SupportWorld(get_scenario("happy-path"))
    assert world.call("real_payment_api", {})["error"] == "tool_not_allowed"
    assert world.call("issue_refund", {"order_id": "external-order"})["error"] == (
        "synthetic_order_not_found")
    assert world.effects == []


def test_results_are_json_serializable_with_sequential_steps():
    result = run_scenario(get_scenario("timeout-after-commit"), "fixed")
    assert json.loads(json.dumps(result)) == result
    assert [event["step"] for event in result["trace"]] == list(range(1, len(result["trace"]) + 1))
