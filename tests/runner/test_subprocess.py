from __future__ import annotations

import sys
from pathlib import Path

from runledger.runner.subprocess import AgentProcess


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
