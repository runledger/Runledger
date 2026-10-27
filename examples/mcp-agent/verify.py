"""Exercise the installed upstream Agent and write local acceptance evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SCENARIOS = {
    "missing-field": "json_schema",
    "wrong-order": "call_order",
    "extra-tool": "max_tool_calls",
}


def run_check(scenario: str, destination: Path) -> dict:
    outcome = {"scenario": scenario, "verified": False}
    try:
        # Do not forward API keys, tracing configuration, or other credentials
        # into the example. Keep only variables needed to locate local runtimes.
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
                                          "HOME", "USERPROFILE", "TMP", "TEMP", "TMPDIR", "LANG", "LC_ALL"}}
        environment["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            [sys.executable, "-m", "runledger", "run", str(ROOT / "evals" / scenario),
             "--mode", "replay", "--output-dir", str(destination)],
            cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=45,
        )
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "console.txt").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        outcome["exit_code"] = completed.returncode
        paths = list(destination.rglob("summary.json"))
        assert len(paths) == 1, f"Expected one summary, got {len(paths)}; see console.txt"
        summary_path = paths[0]
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        events = [json.loads(line) for line in summary_path.with_name("run.jsonl").read_text(encoding="utf-8").splitlines()]
        case = summary["cases"][0]
        calls = [event["name"] for event in events if event["type"] == "tool_call"]
        lifecycle = [event["data"]["action"] for event in events
                     if event["type"] == "log" and event.get("message") == "upstream Agent lifecycle"]
        guard = next(event["data"] for event in events
                     if event["type"] == "log" and event.get("message") == "Replay network guard verified")
        assert guard == {"fetch_blocked": True, "socket_blocked": True, "tls_blocked": True}, "Outbound network guard failed"
        outcome.update({
            "case_status": case["status"], "tool_calls": calls,
            "failure_reason": case["failure_reason"],
            "artifact_directory": (Path(destination.name) / summary_path.parent.relative_to(destination)).as_posix(),
            "upstream_lifecycle_events": lifecycle,
            "network_denial_verified": guard,
        })
        assert "agent:start:task" in lifecycle, "Upstream Agent did not start"
        assert lifecycle.count("agent:tool:call") == len(calls), "Upstream tool dispatch was bypassed"

        if scenario == "pass":
            assert completed.returncode == 0 and case["status"] == "pass", "Expected passing CLI result"
            assert calls == ["search_docs", "read_doc"], f"Unexpected tool sequence: {calls}"
            assert "agent:end:task" in lifecycle, "Upstream Agent did not finish"
            final = next(event["output"] for event in events if event["type"] == "final_output")
            assert final == json.loads((ROOT / "fixtures/model-responses.json").read_text(encoding="utf-8"))["finalOutput"]
            signature = {"calls": [{"name": event["name"], "args": event["args"]}
                                    for event in events if event["type"] == "tool_call"], "output": final}
            outcome["behavior_sha256"] = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        else:
            assert completed.returncode == 1 and case["status"] == "fail", "Expected a contract failure, not a startup error"
            expected = SCENARIOS[scenario]
            if scenario == "extra-tool":
                fields = [item["field"] for event in events if event["type"] == "budget_failure" for item in event["failures"]]
                assert expected in fields, f"Expected {expected}, got {fields}"
                assert len([event for event in events if event["type"] == "tool_result"]) == 2, "Excess call was dispatched"
            else:
                failures = [item["type"] for item in case["failed_assertions"] or []]
                assert expected in failures, f"Expected {expected}, got {failures}"
            outcome["expected_gate"] = expected
        outcome["verified"] = True
    except (AssertionError, OSError, subprocess.TimeoutExpired, ValueError, KeyError, StopIteration) as exc:
        outcome["error"] = str(exc)
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, help="New evidence directory (must not exist)")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    output = (args.output_dir or ROOT / "runledger_out" / f"acceptance-{stamp}").resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Local automated integration checks; no human developer trial was performed.",
        "credentials_forwarded": False,
        "upstream": {"package": "@joshuacalpuerto/mcp-agent", "version": "1.1.1",
                     "revision": "28946564ef1bcd001b8e49f3f62ba3a4c2dec258"},
        "runledger_version": importlib.metadata.version("runledger"),
        "checks": [], "passed": False,
    }
    try:
        node = shutil.which("node")
        assert node, "Install Node.js 22 or newer"
        version = subprocess.check_output([node, "--version"], text=True).strip()
        report["node_version"] = version
        assert int(version.lstrip("v").split(".")[0]) >= 22, "Use Node.js 22 or newer"
        upstream = ROOT / "node_modules/@joshuacalpuerto/mcp-agent/package.json"
        assert upstream.is_file(), "Run npm --prefix examples/mcp-agent ci --ignore-scripts first"
        assert json.loads(upstream.read_text(encoding="utf-8"))["version"] == "1.1.1"
        for index in range(args.repeats):
            report["checks"].append(run_check("pass", output / f"pass-{index + 1:02}"))
        for scenario in SCENARIOS:
            report["checks"].append(run_check(scenario, output / scenario))
        passed_runs = [item for item in report["checks"] if item["scenario"] == "pass" and item["verified"]]
        caught = [item for item in report["checks"] if item["scenario"] != "pass" and item["verified"]]
        report["passing_replays"] = len(passed_runs)
        report["expected_failures_caught"] = len(caught)
        report["unchanged_behavior"] = len({item["behavior_sha256"] for item in passed_runs}) == 1
        report["passed"] = len(passed_runs) == args.repeats and len(caught) == 3 and report["unchanged_behavior"]
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as exc:
        report["error"] = str(exc)
    report_path = output / "acceptance.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{'PASS' if report['passed'] else 'FAIL'}: {report.get('passing_replays', 0)}/{args.repeats} unchanged replays; "
          f"{report.get('expected_failures_caught', 0)}/3 deliberate regressions caught")
    print(f"Evidence: {report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
