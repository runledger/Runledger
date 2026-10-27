from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from runledger.runner.subprocess import (
    AgentDeadlineExceeded, AgentProcess, AgentProcessError, _prefer_available_python,
)


def _write_agent(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "",
                "def send(payload):",
                "    sys.stdout.write(json.dumps(payload) + \"\\n\")",
                "    sys.stdout.flush()",
                "",
                "for line in sys.stdin:",
                "    line = line.strip()",
                "    if not line:",
                "        continue",
                "    msg = json.loads(line)",
                "    if msg.get(\"type\") == \"task_start\":",
                "        send({\"type\": \"tool_call\", \"name\": \"search_docs\", \"call_id\": \"c1\", \"args\": {\"q\": \"hello\"}})",
                "    elif msg.get(\"type\") == \"tool_result\":",
                "        send({\"type\": \"final_output\", \"output\": {\"status\": \"ok\"}})",
                "        break",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_missing_agent_command_is_actionable() -> None:
    agent = AgentProcess(["runledger-missing-python", "agent/agent.py"])
    with pytest.raises(AgentProcessError) as exc_info:
        agent.start()
    message = str(exc_info.value)
    assert "Traceback" not in message
    assert "runledger-missing-python" in message
    assert "not found" in message
    assert "suite.yaml" in message
    assert "python3" in message


def test_missing_python_named_command_mentions_python3(tmp_path: Path) -> None:
    missing = tmp_path / "python"
    agent = AgentProcess([str(missing), "agent/agent.py"])
    with pytest.raises(AgentProcessError) as exc_info:
        agent.start()
    message = str(exc_info.value)
    assert "python" in message
    assert "python3" in message
    assert "PATH" in message
    assert "suite.yaml" in message
    assert "runledger init --force" in message


def test_unrunnable_agent_command_is_actionable(tmp_path: Path) -> None:
    program = tmp_path / "agent-bin"
    program.write_text("not a program\n", encoding="utf-8")
    program.chmod(0o644)
    agent = AgentProcess([str(program)])
    with pytest.raises(AgentProcessError) as exc_info:
        agent.start()
    message = str(exc_info.value)
    # Windows reports an invalid executable; POSIX reports missing permission.
    assert "not executable" in message or "Failed to start agent command" in message
    assert str(program) in message or repr(str(program)) in message
    assert "suite.yaml" in message

    bad = tmp_path / "bad-elf"
    bad.write_bytes(b"\x7fELF\x00not-a-real-binary")
    bad.chmod(0o755)
    agent = AgentProcess([str(bad)])
    with pytest.raises(AgentProcessError) as exc_info:
        agent.start()
    message = str(exc_info.value)
    assert "Failed to start agent command" in message
    assert "suite.yaml" in message
    assert "Traceback" not in message


def test_empty_agent_command_is_actionable() -> None:
    agent = AgentProcess([])
    with pytest.raises(AgentProcessError) as exc_info:
        agent.start()
    message = str(exc_info.value)
    assert "empty" in message.lower()
    assert "suite.yaml" in message


def test_agent_process_roundtrip(tmp_path: Path) -> None:
    agent_path = tmp_path / "agent.py"
    _write_agent(agent_path)

    command = [sys.executable, str(agent_path)]
    with AgentProcess(command, timeout_s=2) as agent:
        agent.send({"type": "task_start", "task_id": "t1", "input": {"prompt": "hi"}})
        tool_call = agent.recv()
        assert tool_call.type == "tool_call"
        assert tool_call.name == "search_docs"
        assert tool_call.args == {"q": "hello"}

        agent.send({"type": "tool_result", "call_id": "c1", "ok": True, "result": {"hits": []}})
        final = agent.recv()
        assert final.type == "final_output"
        assert final.output["status"] == "ok"


@pytest.mark.parametrize(
    ("command", "available", "expected"),
    [
        (["python", "agent.py"], {"python3"}, ["python3", "agent.py"]),
        (["python3", "agent.py"], {"python"}, ["python", "agent.py"]),
        (["python3.exe", "agent.py"], {"python"}, ["python", "agent.py"]),
        (["python", "agent.py"], {"python", "python3"}, ["python", "agent.py"]),
        (["/missing/python", "agent.py"], {"python3"}, ["/missing/python", "agent.py"]),
        (["C:\\missing\\python3.exe"], {"python"}, ["C:\\missing\\python3.exe"]),
    ],
)
def test_python_launcher_fallback(command, available, expected, monkeypatch) -> None:
    monkeypatch.setattr(
        "runledger.runner.subprocess.shutil.which",
        lambda name: name if name in available else None,
    )
    assert _prefer_available_python(command) == expected


def test_utf8_protocol_roundtrip(tmp_path: Path) -> None:
    agent_path = tmp_path / "unicode_agent.py"
    agent_path.write_text(
        "import json, sys\n"
        "request = json.loads(sys.stdin.readline())\n"
        "print(json.dumps({'type': 'final_output', 'output': request['input']}, "
        "ensure_ascii=False), flush=True)\n",
        encoding="utf-8",
    )
    value = "Bonjour, 世界 🌍"
    with AgentProcess([sys.executable, str(agent_path)], timeout_s=3) as agent:
        agent.send({"type": "task_start", "task_id": "unicode", "input": {"text": value}})
        result = agent.recv()
    assert result.output == {"text": value}


def test_deadline_interrupts_blocked_stdin_write(tmp_path: Path) -> None:
    agent_path = tmp_path / "never_reads.py"
    agent_path.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    start = time.monotonic()
    with AgentProcess(
        [sys.executable, str(agent_path)], timeout_s=None, deadline=start + 0.5
    ) as agent:
        process = agent._process
        with pytest.raises(AgentDeadlineExceeded):
            agent.send({"type": "task_start", "task_id": "blocked", "input": {"x": "x" * 1000000}})
    assert time.monotonic() - start < 3
    assert process is not None and process.poll() is not None


def test_close_stops_descendants_after_parent_exits(tmp_path: Path) -> None:
    marker = tmp_path / "orphan_survived"
    child_code = (
        f"import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).touch()"
    )
    agent_path = tmp_path / "spawns_child.py"
    agent_path.write_text(
        "import json, subprocess, sys\n"
        "json.loads(sys.stdin.readline())\n"
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}])\n"
        "print(json.dumps({'type':'final_output','output':{}}),flush=True)\n",
        encoding="utf-8",
    )
    with AgentProcess([sys.executable, str(agent_path)], timeout_s=3) as agent:
        agent.send({"type": "task_start", "task_id": "orphan", "input": {}})
        assert agent.recv().type == "final_output"
        agent._process.wait(timeout=2)
        close_started = time.monotonic()
    assert time.monotonic() - close_started < 1.5
    time.sleep(2.1)
    assert not marker.exists()


@pytest.mark.parametrize("stream", [1, 2], ids=["invalid-protocol", "binary-stderr"])
def test_invalid_utf8_does_not_crash_reader_thread(tmp_path: Path, stream: int) -> None:
    agent_path = tmp_path / "binary_output.py"
    agent_path.write_text(
        f"import os\nos.write({stream}, b'\\xff\\n')\n"
        "print('{\"type\":\"final_output\",\"output\":{}}',flush=True)\n",
        encoding="utf-8",
    )
    with AgentProcess([sys.executable, str(agent_path)], timeout_s=2) as agent:
        if stream == 1:
            with pytest.raises(AgentProcessError, match="decode"):
                agent.recv()
        else:
            assert agent.recv().type == "final_output"
