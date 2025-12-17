from __future__ import annotations

import json
import sys
from pathlib import Path

from runledger.config.models import CaseConfig, SuiteConfig
from runledger.runner.engine import run_case


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


def test_record_mode_writes_cassette(tmp_path: Path) -> None:
    agent_path = tmp_path / "agent.py"
    _write_agent(agent_path)

    suite = SuiteConfig(
        suite_name="demo",
        agent_command=[sys.executable, str(agent_path)],
        mode="record",
        cases_path="cases",
        tool_registry=["search_docs"],
    )
    cassette_path = tmp_path / "cassettes" / "t1.jsonl"
    case = CaseConfig(
        id="t1",
        input={"prompt": "hi"},
        cassette=str(cassette_path),
    )

    result = run_case(suite, case)

    assert result.passed
    assert cassette_path.is_file()
    lines = cassette_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["tool"] == "search_docs"
    assert entry["args"] == {"q": "hello"}
