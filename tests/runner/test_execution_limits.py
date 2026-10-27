from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import pytest

from runledger.config.models import BudgetSpec, CaseConfig, SuiteConfig
from runledger.runner.engine import run_case


def make_case(tmp_path: Path, source: str, *, budget: BudgetSpec | None, mode="replay"):
    agent = tmp_path / "agent.py"
    agent.write_text("import json, sys, time\n" + source, encoding="utf-8")
    cassette = tmp_path / "cassette.jsonl"
    cassette.write_text("", encoding="utf-8")
    suite = SuiteConfig(
        suite_name="limits", agent_command=[sys.executable, str(agent)], mode=mode,
        cases_path="cases", tool_registry=[], budgets=budget,
    )
    case = CaseConfig(id="limits", input={}, cassette=str(cassette))
    return suite, case


@pytest.mark.parametrize("chatty", [False, True], ids=["silent", "chatty"])
def test_case_deadline_stops_agent(tmp_path: Path, chatty: bool) -> None:
    source = "json.loads(sys.stdin.readline())\n"
    if chatty:
        source += (
            "while True:\n"
            " print(json.dumps({'type':'log','level':'info','message':'still running'}), flush=True)\n"
            " time.sleep(0.01)\n"
        )
    else:
        source += "time.sleep(30)\n"
    suite, case = make_case(tmp_path, source, budget=BudgetSpec(max_wall_ms=500))
    start = time.monotonic()
    result = run_case(suite, case)
    assert time.monotonic() - start < 3
    assert result.failure is not None and result.failure.type == "budget_exceeded"
    assert "max_wall_ms" in result.failure.message
    assert result.output is None
    if chatty:
        assert any(event["type"] == "log" for event in result.trace)


def install_tools(tmp_path, monkeypatch, source: str) -> str:
    module = "execution_limit_tools"
    (tmp_path / f"{module}.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return module


def two_calls_source() -> str:
    return (
        "json.loads(sys.stdin.readline())\n"
        "results=[]\n"
        "for i in range(2):\n"
        " print(json.dumps({'type':'tool_call','name':'ping','call_id':str(i),'args':{}}),flush=True)\n"
        " results.append(json.loads(sys.stdin.readline()))\n"
        "print(json.dumps({'type':'final_output','output':{'results':results}}),flush=True)\n"
    )


@pytest.mark.parametrize("limit_kind", ["calls", "errors"])
def test_no_tool_executes_after_budget_is_exhausted(tmp_path, monkeypatch, limit_kind) -> None:
    marker = tmp_path / "executions.txt"
    source = (
        "from pathlib import Path\n"
        "def ping(args):\n"
        f" with Path({str(marker)!r}).open('a') as handle: handle.write('call\\n')\n"
    )
    source += " raise ValueError('tool failed')\n" if limit_kind == "errors" else " return {}\n"
    source += "TOOLS={'ping':ping}\n"
    module = install_tools(tmp_path, monkeypatch, source)
    budget = BudgetSpec(max_tool_errors=0) if limit_kind == "errors" else BudgetSpec(max_tool_calls=1)
    suite, case = make_case(tmp_path, two_calls_source(), budget=budget, mode="live")
    suite.tool_registry, suite.tool_module = ["ping"], module
    result = run_case(suite, case)
    assert result.failure is not None and result.failure.type == "budget_exceeded"
    assert marker.read_text().splitlines() == ["call"]
    assert result.output is None
    if limit_kind == "errors":
        assert result.tool_errors == 1
        assert any(event["type"] == "tool_result" and not event["ok"] for event in result.trace)


def test_zero_call_budget_does_not_execute_first_call(tmp_path, monkeypatch) -> None:
    marker = tmp_path / "should_not_exist"
    module = install_tools(
        tmp_path, monkeypatch,
        "from pathlib import Path\n"
        f"def ping(args):\n Path({str(marker)!r}).touch()\n return {{}}\nTOOLS={{'ping':ping}}\n",
    )
    suite, case = make_case(tmp_path, two_calls_source(), budget=BudgetSpec(max_tool_calls=0), mode="live")
    suite.tool_registry, suite.tool_module = ["ping"], module
    result = run_case(suite, case)
    assert result.failure is not None and result.failure.type == "budget_exceeded"
    assert not marker.exists()


def test_deadline_kills_blocked_tool_and_child_before_returning(tmp_path, monkeypatch) -> None:
    started, escaped = tmp_path / "started", tmp_path / "escaped"
    child_code = f"import time; from pathlib import Path; time.sleep(2); Path({str(escaped)!r}).touch()"
    module = install_tools(
        tmp_path, monkeypatch,
        "import subprocess, sys, time\nfrom pathlib import Path\n"
        "def ping(args):\n"
        f" Path({str(started)!r}).touch()\n"
        f" subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
        " time.sleep(30)\n"
        f" Path({str(escaped)!r}).touch()\n"
        " return {}\nTOOLS={'ping':ping}\n",
    )
    suite, case = make_case(tmp_path, two_calls_source(), budget=BudgetSpec(max_wall_ms=1500), mode="live")
    suite.tool_registry, suite.tool_module = ["ping"], module
    start = time.monotonic()
    result = run_case(suite, case)
    assert time.monotonic() - start < 4
    assert started.exists(), "The tool must have started for this cancellation test to be meaningful"
    assert result.failure is not None and result.failure.type == "budget_exceeded"
    time.sleep(2.1)
    assert not escaped.exists(), "Neither the tool nor its child may keep running after cancellation"


def test_worker_preserves_state_and_handles_prints_and_unicode(tmp_path, monkeypatch) -> None:
    module = install_tools(
        tmp_path, monkeypatch,
        "import os, subprocess, sys\nprint('import log')\ncount=0\n"
        "def ping(args):\n"
        " global count\n count+=1\n print('tool log')\n"
        " os.write(1, b'native log\\n')\n"
        " subprocess.run([sys.executable, '-c', \"print('child log')\"], check=True)\n"
        " return {'count':count,'text':'世界 🌍'}\nTOOLS={'ping':ping}\n",
    )
    suite, case = make_case(tmp_path, two_calls_source(), budget=None, mode="record")
    suite.tool_registry, suite.tool_module = ["ping"], module
    result = run_case(suite, case)
    assert result.passed, result.failure
    assert [item["result"]["count"] for item in result.output["results"]] == [1, 2]
    assert result.output["results"][0]["result"]["text"] == "世界 🌍"
    entries = [json.loads(line) for line in Path(case.cassette).read_text(encoding="utf-8").splitlines()]
    assert [entry["result"]["count"] for entry in entries] == [1, 2]


def test_tool_registry_import_is_bounded(tmp_path, monkeypatch) -> None:
    module = install_tools(tmp_path, monkeypatch, "import time\ntime.sleep(30)\nTOOLS={}\n")
    suite, case = make_case(tmp_path, "time.sleep(30)\n", budget=BudgetSpec(max_wall_ms=500), mode="live")
    suite.tool_module = module
    start = time.monotonic()
    result = run_case(suite, case)
    assert time.monotonic() - start < 3
    assert result.failure is not None and result.failure.type == "budget_exceeded"
