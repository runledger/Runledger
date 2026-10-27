from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from runledger.config.models import CaseConfig, SuiteConfig
from runledger.runner.engine import run_case


def _polling_suite(tmp_path: Path) -> tuple[SuiteConfig, CaseConfig]:
    agent = tmp_path / "agent.py"
    agent.write_text(
        """import json
import sys

start = json.loads(sys.stdin.readline())
responses = []
for index in range(start['input'].get('calls', 2)):
    print(json.dumps({'type': 'tool_call', 'name': 'poll', 'call_id': str(index),
                      'args': {'job': 1}}), flush=True)
    response = json.loads(sys.stdin.readline())
    responses.append({'ok': response['ok'], 'result': response.get('result'),
                      'error': response.get('error')})
print(json.dumps({'type': 'final_output', 'output': {'responses': responses}}), flush=True)
""",
        encoding="utf-8",
    )
    suite = SuiteConfig(
        suite_name="polling",
        agent_command=[sys.executable, str(agent)],
        mode="replay",
        cases_path="cases",
        tool_registry=["poll"],
    )
    case = CaseConfig(id="poll", input={}, cassette=str(tmp_path / "poll.jsonl"))
    return suite, case


def test_record_then_replay_preserves_stateful_polling(tmp_path: Path, monkeypatch) -> None:
    suite, case = _polling_suite(tmp_path)
    module_name = "runledger_review_polling_tools"
    (tmp_path / f"{module_name}.py").write_text(
        """calls = 0
def poll(args):
    global calls
    calls += 1
    return {'state': 'pending' if calls == 1 else 'done'}
TOOLS = {'poll': poll}
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    recorded = run_case(
        suite.model_copy(update={"mode": "record", "tool_module": module_name}), case
    )
    assert recorded.passed, recorded.failure
    assert recorded.output == {
        "responses": [
            {"ok": True, "result": {"state": "pending"}, "error": None},
            {"ok": True, "result": {"state": "done"}, "error": None},
        ]
    }
    cassette_before = Path(case.cassette).read_bytes()

    # Each run owns its playback cursor; replay never modifies the saved cassette.
    for _ in range(2):
        replayed = run_case(suite, case)
        assert replayed.passed, replayed.failure
        assert replayed.output == recorded.output
    assert Path(case.cassette).read_bytes() == cassette_before


def test_replay_retries_use_recorded_error_then_success(tmp_path: Path) -> None:
    suite, case = _polling_suite(tmp_path)
    entries = [
        {"tool": "poll", "args": {"job": 1}, "ok": False, "error": "retry later"},
        {"tool": "poll", "args": {"job": 1}, "ok": True, "result": {"state": "done"}},
    ]
    Path(case.cassette).write_text(
        "\n".join(json.dumps(entry) for entry in entries), encoding="utf-8"
    )
    replayed = run_case(suite, case)
    assert replayed.passed, replayed.failure
    assert replayed.tool_errors == 1
    assert replayed.output == {
        "responses": [
            {"ok": False, "result": None, "error": "retry later"},
            {"ok": True, "result": {"state": "done"}, "error": None},
        ]
    }


@pytest.mark.parametrize("calls", [2, 3])
def test_replay_fails_when_matching_entries_are_exhausted(tmp_path: Path, calls: int) -> None:
    suite, case = _polling_suite(tmp_path)
    entry = {"tool": "poll", "args": {"job": 1}, "ok": True, "result": {"state": "done"}}
    Path(case.cassette).write_text(json.dumps(entry) + "\n", encoding="utf-8")
    replayed = run_case(suite, case.model_copy(update={"input": {"calls": calls}}))
    assert not replayed.passed
    assert replayed.failure is not None
    assert replayed.failure.type == "cassette_mismatch"
    assert replayed.tool_calls == 2
    assert replayed.output is None
