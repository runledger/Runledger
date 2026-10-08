from __future__ import annotations

import sys
from pathlib import Path

import pytest

from runledger.runner.subprocess import AgentProcess, AgentProcessError


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
    assert "not executable" in message
    assert str(program) in message
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
