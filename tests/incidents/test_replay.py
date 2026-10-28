from __future__ import annotations

import json
import sys
import time
from copy import deepcopy
from pathlib import Path

import pytest

from runledger.incidents import replay
from runledger.incidents.replay import evaluate_incident, replay_incident


def incident() -> dict:
    args = {"order_id": "redacted-order-1", "amount_cents": 4900}
    return {"id": "incident-opaque", "input": {"order_id": "redacted-order-1"},
            "effects_complete": True,
            "events": [
                {"type": "tool_call", "call_id": "c1", "name": "issue_refund", "args": args},
                {"type": "business_effect", "call_id": "c1", "effect": {
                    "type": "refund", "order_id": "redacted-order-1", "amount_cents": 4900,
                    "refund_id": "redacted-refund-1"}},
                {"type": "tool_result", "call_id": "c1", "ok": False, "result": None,
                 "error": "provider_timeout"},
                {"type": "tool_call", "call_id": "c2", "name": "issue_refund", "args": deepcopy(args)},
                {"type": "business_effect", "call_id": "c2", "effect": {
                    "type": "refund", "order_id": "redacted-order-1", "amount_cents": 4900,
                    "refund_id": "redacted-refund-2"}},
                {"type": "tool_result", "call_id": "c2", "ok": True,
                 "result": {"refund_id": "redacted-refund-2"}, "error": None},
                {"type": "final_output", "output": {"status": "refunded", "refund_id": "redacted-refund-2"}},
            ], "assertions": [
                {"id": "one-refund", "type": "effect_count", "effect_type": "refund", "group_by": "order_id", "max": 1},
                {"id": "status", "type": "output_equals", "path": "/status", "value": "refunded"},
                {"id": "receipt", "type": "required_output", "fields": ["refund_id"]},
                {"id": "tool-errors", "type": "max_tool_errors", "max": 1},
            ]}


def command(tmp_path: Path, mode: str = "normal") -> list[str]:
    source = tmp_path / "adapter.py"
    source.write_text('''import json
import sys
import time

MODE = ''' + repr(mode) + '''
def send(value):
    print(json.dumps(value), flush=True)
start = json.loads(sys.stdin.readline())
if MODE == "timeout":
    time.sleep(10)
if MODE == "private_error":
    print("private-new-secret", file=sys.stderr, flush=True)
    print("private-new-secret", flush=True)
    raise SystemExit(1)
if MODE == "logs":
    for _ in range(10):
        send({"type":"log", "level":"info", "message":"private-new-secret"})
for i in range(2):
    if MODE == "missing" and i == 1:
        break
    args = {"order_id":start["input"]["order_id"], "amount_cents":4900}
    if MODE == "args":
        args["private-new-secret"] = "private-new-secret"
    name = "other_tool" if MODE == "wrong_tool" else "issue_refund"
    call_id = "same" if MODE == "same_id" else "adapter-" + str(i)
    send({"type":"tool_call", "name":name, "call_id":call_id, "args":args})
    response = json.loads(sys.stdin.readline())
    if i == 0:
        assert not response["ok"] and response["error"] == "provider_timeout"
    else:
        assert response["ok"] and response["result"]["refund_id"] == "redacted-refund-2"
if MODE == "extra":
    send({"type":"tool_call", "name":"private-new-secret", "call_id":"extra", "args":{}})
    json.loads(sys.stdin.readline())
if MODE == "crash":
    raise RuntimeError("private-new-secret")
if MODE == "task_error":
    send({"type":"task_error", "message":"expected_error"})
else:
    send({"type":"final_output", "output": {
        "status":"private-new-secret" if MODE == "output" else "refunded",
        "refund_id":"redacted-refund-2"}})
''', encoding="utf-8")
    return [sys.executable, str(source)]


def test_evidence_evaluation_counts_effects_separately_from_successful_responses():
    result = evaluate_incident(incident())
    assert result["passed"] is False
    assert result["tool_calls"] == 2
    assert result["tool_errors"] == 1
    assert len(result["effects"]) == 2
    assert result["assertions"][0]["actual"]["total"] == 2
    assert result["assertions"][0]["passed"] is False
    assert all(check["passed"] for check in result["assertions"][1:])


@pytest.mark.parametrize("complete", [None, False])
def test_incomplete_effect_ledger_is_inconclusive_not_zero_effects_proof(complete):
    data = incident()
    data["effects_complete"] = complete
    data["events"] = [event for event in data["events"] if event["type"] != "business_effect"]
    result = evaluate_incident(data)
    assert result["passed"] is False
    assert result["assertions"][0]["status"] == "inconclusive"


def test_business_rules_still_evaluate_after_task_error_or_no_final_output():
    data = incident()
    data["events"][-1] = {"type": "task_error", "message": "stopped"}
    result = evaluate_incident(data)
    assert result["passed"] is False
    assert result["error"] == "stopped"
    assert result["assertions"][0]["passed"] is False
    assert result["assertions"][1]["passed"] is False
    assert result["assertions"][2]["passed"] is False
    data["events"].pop()
    assert evaluate_incident(data)["error"] == "missing_final_output"


def test_effect_groups_do_not_merge_boolean_and_integer_values():
    data = incident()
    data["events"][1]["effect"]["order_id"] = True
    data["events"][4]["effect"]["order_id"] = 1
    result = evaluate_incident(data)
    assert result["assertions"][0]["passed"] is True
    assert result["assertions"][0]["actual"]["group_counts"] == [1, 1]
    del data["events"][1]["effect"]["order_id"]
    assert evaluate_incident(data)["assertions"][0]["passed"] is False


def test_output_values_are_type_strict_and_json_pointers_handle_arrays_and_escapes():
    data = incident()
    data["events"][-1]["output"] = {"a/b": [{"~value": 1}]}
    data["assertions"] = [{"id": "number", "type": "output_equals", "path": "/a~1b/0/~0value", "value": True}]
    assert evaluate_incident(data)["passed"] is False
    data["assertions"][0]["value"] = 1
    assert evaluate_incident(data)["passed"] is True


def test_positive_minimum_never_passes_for_empty_groups():
    data = incident()
    data["assertions"] = [{"id": "minimum", "type": "effect_count", "effect_type": "other", "group_by": "order_id", "min": 1, "max": 1}]
    assert evaluate_incident(data)["passed"] is False


def test_identical_repeated_calls_consume_distinct_recorded_responses_once(tmp_path, monkeypatch):
    import runledger.tools.registry

    def no_live_tools(*args, **kwargs):
        raise AssertionError("Live tools must never be resolved")
    monkeypatch.setattr(runledger.tools.registry, "resolve_tools", no_live_tools)
    original = incident()
    data = deepcopy(original)
    data["command"] = ["never-execute-a-command-from-data"]
    result = replay_incident(data, command(tmp_path))
    assert result["matched"] is True
    assert result["verdict"] == "reproduced"
    assert result["observed"]["passed"] is False
    assert result["observed"] == result["expected"]
    assert result["trace"] == original["events"]
    assert result["consumed_tool_calls"] == 2


def test_delayed_audit_effects_keep_the_original_capture_order(tmp_path):
    data = incident()
    first_effect = data["events"].pop(1)
    data["events"].insert(-1, first_effect)
    result = replay_incident(data, command(tmp_path))
    assert result["matched"] is True
    assert result["trace"] == data["events"]
    assert result["observed"] == result["expected"]


@pytest.mark.parametrize("mode,kind", [
    ("missing", "missing_tool_calls"),
    ("extra", "extra_tool_call"),
    ("wrong_tool", "tool_call_mismatch"),
    ("args", "tool_call_mismatch"),
    ("output", "terminal_mismatch"),
    ("same_id", "invalid_call_id"),
])
def test_unrecorded_or_changed_behavior_is_divergence_not_a_verified_fix(tmp_path, mode, kind):
    result = replay_incident(incident(), command(tmp_path, mode))
    assert result["matched"] is False
    assert result["verdict"] == "diverged"
    assert result["first_divergence"]["kind"] == kind
    assert result["observed"]["passed"] is False
    assert "private-new-secret" not in json.dumps(result)


def test_crash_after_commit_keeps_effect_evidence_but_discards_stderr(tmp_path):
    result = replay_incident(incident(), command(tmp_path, "crash"))
    assert result["matched"] is False
    assert result["verdict"] == "agent_error"
    assert len(result["observed"]["effects"]) == 2
    assert result["observed"]["assertions"][0]["passed"] is False
    assert "private-new-secret" not in json.dumps(result)


def test_a_recorded_explicit_task_error_can_be_reproduced(tmp_path):
    data = incident()
    data["events"][-1] = {"type": "task_error", "message": "expected_error"}
    result = replay_incident(data, command(tmp_path, "task_error"))
    assert result["matched"] is True
    assert result["observed"]["error"] == "expected_error"
    assert result["observed"]["passed"] is False


def test_task_error_payload_is_withheld_and_changed_message_diverges():
    data = incident()
    data["events"] = [{"type": "task_error", "message": "expected_error"}]
    data["assertions"] = [{"id": "errors", "type": "max_tool_errors", "max": 0}]
    for message, matched in (("expected_error", True), ("private-new-secret", False)):
        source = "import json; print(json.dumps(" + repr({"type": "task_error", "message": message,
                                                          "data": {"secret": "private-new-secret"}}) + "), flush=True)"
        result = replay_incident(data, [sys.executable, "-c", source])
        assert result["matched"] is matched
        assert result["observed"]["passed"] is False
        assert "private-new-secret" not in json.dumps(result)


def test_agent_logs_are_ignored_and_cannot_forge_business_effects(tmp_path):
    result = replay_incident(incident(), command(tmp_path, "logs"))
    assert result["matched"] is True
    assert "private-new-secret" not in json.dumps(result)
    assert len(result["observed"]["effects"]) == 2


def test_private_parse_errors_never_appear_in_evidence(tmp_path):
    result = replay_incident(incident(), command(tmp_path, "private_error"))
    assert result["verdict"] == "agent_error"
    assert "private-new-secret" not in json.dumps(result)


def test_message_budget_and_receive_timeout_stop_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "MAX_MESSAGES", 2)
    result = replay_incident(incident(), command(tmp_path, "logs"))
    assert result["verdict"] == "agent_error"
    assert result["consumed_tool_calls"] == 0
    result = replay_incident(incident(), command(tmp_path, "timeout"), timeout_s=0.05)
    assert result["verdict"] == "agent_error"
    assert result["matched"] is False


@pytest.mark.parametrize("value", [None, [], "python script.py", [None], [""], [1]])
def test_a_trusted_local_command_must_be_explicit(value):
    with pytest.raises(ValueError, match="explicit"):
        replay_incident(incident(), value)


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf"), 31, "5"])
def test_timeout_is_bounded_and_numeric(value):
    with pytest.raises(ValueError, match="timeout"):
        replay_incident(incident(), [sys.executable], timeout_s=value)


def test_slow_stdin_reader_cannot_block_initial_task_delivery():
    data = incident()
    data["input"]["captured_context"] = ["x" * 64000] * 24
    started = time.monotonic()
    result = replay_incident(data, [sys.executable, "-c", "import time; time.sleep(10)"], timeout_s=0.1)
    assert time.monotonic() - started < 3
    assert result["verdict"] == "agent_error"
    assert result["consumed_tool_calls"] == 0


def test_slow_stdin_reader_cannot_block_recorded_result_delivery():
    data = incident()
    data["events"][2]["result"] = ["x" * 64000] * 24
    source = '''import sys, json, time
json.loads(sys.stdin.readline())
print(json.dumps({"type":"tool_call", "call_id":"c", "name":"issue_refund",
                  "args":{"order_id":"redacted-order-1", "amount_cents":4900}}), flush=True)
time.sleep(10)
'''
    started = time.monotonic()
    result = replay_incident(data, [sys.executable, "-c", source], timeout_s=0.15)
    assert time.monotonic() - started < 3
    assert result["verdict"] == "agent_error"
    assert result["observed"]["effects"]


@pytest.mark.parametrize("mode", ["oversized", "blank_flood", "json_flood", "invalid_utf8", "duplicate_key"])
def test_invalid_or_flooded_stdout_stops_with_no_private_values(mode, monkeypatch):
    monkeypatch.setattr(replay, "MAX_MESSAGE_BYTES", 1024)
    monkeypatch.setattr(replay, "MAX_MESSAGES", 20)
    scripts = {
        "oversized": 'sys.stdout.write("private-new-secret" * 1000); sys.stdout.flush()',
        "blank_flood": 'sys.stdout.write("\\n" * 1000); sys.stdout.flush()',
        "json_flood": 'print((json.dumps({"type":"log","level":"info","message":"private-new-secret"}) + "\\n") * 1000, flush=True)',
        "invalid_utf8": 'sys.stdout.buffer.write(b"private-new-secret\\xff\\n"); sys.stdout.buffer.flush()',
        "duplicate_key": 'print(\'{"type":"log","level":"info","message":"private-new-secret","message":"other"}\', flush=True)',
    }
    source = 'import sys, json, time\n' + scripts[mode] + '\ntime.sleep(10)'
    started = time.monotonic()
    result = replay_incident(incident(), [sys.executable, "-c", source], timeout_s=0.2)
    assert time.monotonic() - started < 3
    assert result["verdict"] == "agent_error"
    assert "private-new-secret" not in json.dumps(result)


def test_large_unterminated_stderr_does_not_block_or_leak(tmp_path):
    cmd = command(tmp_path)
    adapter = Path(cmd[-1])
    source = adapter.read_text(encoding="utf-8")
    adapter.write_text(source.replace('start = json.loads(sys.stdin.readline())',
                      'sys.stderr.write("private-new-secret" * 100000)\nsys.stderr.flush()\n'
                      'start = json.loads(sys.stdin.readline())'), encoding="utf-8")
    result = replay_incident(incident(), cmd)
    assert result["matched"] is True
    assert "private-new-secret" not in json.dumps(result)


def test_total_deadline_applies_to_continuous_messages(monkeypatch):
    monkeypatch.setattr(replay, "MAX_SECONDS", 0.2)
    source = '''import sys, json, time
json.loads(sys.stdin.readline())
while True:
    print(json.dumps({"type":"log","level":"info","message":"still running"}), flush=True)
    time.sleep(0.04)
'''
    started = time.monotonic()
    result = replay_incident(incident(), [sys.executable, "-c", source], timeout_s=0.15)
    assert time.monotonic() - started < 3
    assert result["verdict"] == "agent_error"


def test_unicode_jsonl_is_utf8_on_every_platform():
    value = "東京—café ☃"
    data = {"id": "unicode-example", "input": {"value": value}, "effects_complete": False,
            "events": [
                {"type": "tool_call", "call_id": "c1", "name": "lookup", "args": {"value": value}},
                {"type": "tool_result", "call_id": "c1", "ok": True, "result": {"value": value}, "error": None},
                {"type": "final_output", "output": {"value": value}},
            ], "assertions": [{"id": "unicode", "type": "output_equals", "path": "/value", "value": value}]}
    source = '''import json, sys
def send(data):
    sys.stdout.buffer.write((json.dumps(data, ensure_ascii=False) + "\\n").encode("utf-8"))
    sys.stdout.buffer.flush()
task = json.loads(sys.stdin.readline())
send({"type":"tool_call", "name":"lookup", "call_id":"adapter-id", "args":task["input"]})
response = json.loads(sys.stdin.readline())
send({"type":"final_output", "output":response["result"]})
'''
    result = replay_incident(data, [sys.executable, "-c", source])
    assert result["matched"] is True
    assert result["observed"]["passed"] is True


def test_real_production_example_import_replays_and_gate_fails(tmp_path):
    from runledger.incidents.cli import main

    project = Path(__file__).resolve().parents[2]
    imported = tmp_path / "imported"
    replayed = tmp_path / "replayed"
    assert main(["import", str(project / "examples/incidents/production-example.json"),
                 "--out", str(imported)]) == 0
    code = main(["replay", str(imported / "incident.json"), "--agent-command",
                 json.dumps([sys.executable, str(project / "examples/incidents/replay_agent.py")]),
                 "--out", str(replayed), "--gate"])
    assert code == 1
    result = json.loads((replayed / "replay.json").read_text(encoding="utf-8"))
    assert result["matched"] is True
    assert result["consumed_tool_calls"] == 3
    assert result["observed"]["passed"] is False
    assert len(result["observed"]["effects"]) == 2


def test_replay_sets_child_utf8_even_with_an_ascii_parent_environment(monkeypatch):
    monkeypatch.setenv("PYTHONIOENCODING", "ascii")
    value = "世界 café"
    data = {"id": "unicode-child", "input": {"value": value}, "effects_complete": False,
            "events": [{"type": "final_output", "output": {"value": value}}],
            "assertions": [{"id": "unicode", "type": "output_equals", "path": "/value", "value": value}]}
    source = '''import json, sys
task = json.loads(sys.stdin.readline())
print(json.dumps({"type":"final_output", "output":task["input"]}, ensure_ascii=False), flush=True)
'''
    result = replay_incident(data, [sys.executable, "-c", source])
    assert result["matched"] is True
    assert result["observed"]["passed"] is True


def test_replay_stops_inherited_descendants_after_terminal_output(tmp_path):
    started, escaped = tmp_path / "child-started", tmp_path / "child-escaped"
    child = ("import time; from pathlib import Path; "
             f"Path({str(started)!r}).touch(); time.sleep(1.5); Path({str(escaped)!r}).touch()")
    source = f'''import json, sys, subprocess, time
from pathlib import Path
json.loads(sys.stdin.readline())
subprocess.Popen([sys.executable, "-c", {child!r}])
deadline = time.monotonic() + 5
while not Path({str(started)!r}).exists():
    if time.monotonic() >= deadline:
        raise SystemExit(1)
    time.sleep(0.01)
print(json.dumps({{"type":"final_output", "output":{{"status":"done"}}}}), flush=True)
'''
    data = {"id": "descendant-cleanup", "input": {}, "effects_complete": False,
            "events": [{"type": "final_output", "output": {"status": "done"}}],
            "assertions": [{"id": "done", "type": "output_equals", "path": "/status", "value": "done"}]}
    before = time.monotonic()
    result = replay_incident(data, [sys.executable, "-c", source])
    assert time.monotonic() - before < 3
    assert started.exists(), "Child must have started for this cleanup check to be meaningful"
    assert result["matched"] is True
    time.sleep(1.6)
    assert not escaped.exists(), "An inherited child must stop when its replay finishes"
