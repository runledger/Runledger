from __future__ import annotations

import json
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from runledger.artifacts.report import write_report

ATTACK = "<img src=x onerror=window.__reportInjected=true>"
SCRIPT_ATTACK = "</script><script>window.__reportInjected=true</script><!--<script>"


class ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[dict[str, str | None]] = []
        self.data: list[str] = []
        self.in_data = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            attributes = dict(attrs)
            self.scripts.append(attributes)
            self.in_data = attributes.get("id") == "runledger-data"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_data = False

    def handle_data(self, data: str) -> None:
        if self.in_data:
            self.data.append(data)


def _hostile_report(tmp_path: Path) -> tuple[Path, dict]:
    hostile_id = f"case-{ATTACK}"
    trace = [
        {"case_id": hostile_id, "type": kind, "payload": ATTACK + SCRIPT_ATTACK}
        for kind in ["task_start", "tool_call", "tool_result", "final_output", ATTACK]
    ]
    trace.append({"case_id": "safe-case", "type": "final_output", "output": {"ok": True}})
    (tmp_path / "run.jsonl").write_text(
        "\n".join(json.dumps(event) for event in trace), encoding="utf-8"
    )
    summary = {
        "suite": {"name": ATTACK},
        "run": {"run_id": SCRIPT_ATTACK, "mode": ATTACK, "exit_status": ATTACK},
        "generated_at": ATTACK,
        "aggregates": {"cases_pass": ATTACK, "metrics": {"wall_ms": {"p95": ATTACK}}},
        "cases": [
            {
                "id": hostile_id,
                "status": "fail",
                "failure_reason": ATTACK + SCRIPT_ATTACK,
                "wall_ms": ATTACK,
                "tool_calls": ATTACK,
                "tool_errors": ATTACK,
                "tokens_in": ATTACK,
                "tokens_out": ATTACK,
                "cost_usd": ATTACK,
                "steps": ATTACK,
                "assertions": {"failed": ATTACK, "total": ATTACK},
            },
            {
                "id": "safe-case",
                "status": "pass",
                "wall_ms": 1,
                "tool_calls": 0,
                "tool_errors": 0,
            },
        ],
    }
    return write_report(tmp_path, summary=summary), summary


def test_embedded_json_cannot_escape_script_element(tmp_path: Path) -> None:
    report, summary = _hostile_report(tmp_path)
    parser = ScriptParser()
    parser.feed(report.read_text(encoding="utf-8"))

    assert len(parser.scripts) == 2
    assert parser.scripts[0]["id"] == "runledger-data"
    embedded = "".join(parser.data)
    assert "<" not in embedded
    assert json.loads(embedded)["summary"] == summary


def test_report_displays_untrusted_text_and_preserves_filters(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed for report DOM tests; install Node and run npm ci")
    root = Path(__file__).resolve().parents[2]
    probe = subprocess.run(
        [node, "-e", "require.resolve('jsdom')"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode:
        pytest.skip("jsdom is needed for report DOM tests; run npm ci")
    report, _ = _hostile_report(tmp_path)
    result = subprocess.run(
        [node, str(Path(__file__).with_name("check_report_dom.cjs")), str(report)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
