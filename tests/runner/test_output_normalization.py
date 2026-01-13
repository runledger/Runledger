from __future__ import annotations

import json
import sys
from pathlib import Path

from runledger.config.models import AssertionSpec, CaseConfig, NormalizationSpec, SuiteConfig
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
                "        send({\"type\": \"final_output\", \"output\": {\"message\": \"ok\", \"timestamp\": \"2025-01-01T00:00:00Z\"}})",
                "        break",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_output_normalization_applies_before_assertions(tmp_path: Path) -> None:
    agent_path = tmp_path / "agent.py"
    _write_agent(agent_path)

    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )

    cassette_path = tmp_path / "cassettes" / "t1.jsonl"
    cassette_path.parent.mkdir(parents=True, exist_ok=True)
    cassette_path.write_text("", encoding="utf-8")

    suite = SuiteConfig(
        suite_name="demo",
        agent_command=[sys.executable, str(agent_path)],
        mode="replay",
        cases_path="cases",
        tool_registry=[],
        assertions=[AssertionSpec(type="json_schema", schema_path=str(schema_path))],
        normalization=NormalizationSpec(strip_keys=["timestamp"]),
    )
    case = CaseConfig(
        id="t1",
        input={"prompt": "hi"},
        cassette=str(cassette_path),
    )

    result = run_case(suite, case)

    assert result.passed
    assert result.output == {"message": "ok"}
