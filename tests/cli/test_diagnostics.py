"""Exercise diagnostics as public commands, including their JSON and exit contracts."""

from __future__ import annotations

import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from runledger.cli import app

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


@pytest.fixture
def example(tmp_path: Path) -> Path:
    suite = tmp_path / "customer suite"
    shutil.copytree(ROOT / "examples" / "verification", suite)
    config = yaml.safe_load((suite / "suite.yaml").read_text(encoding="utf-8"))
    config["agent_command"][0] = sys.executable
    (suite / "suite.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    return suite


def invoke(command: str, example: Path, *args: str):
    result = runner.invoke(app, [command, str(example), "--json", *args])
    return result, json.loads(result.stdout)


def test_doctor_is_static_unless_probe_is_requested(example: Path, tmp_path: Path) -> None:
    marker = example / "agent-was-executed"
    agent = example / "agent.py"
    original = agent.read_text(encoding="utf-8")
    agent.write_text(
        original.replace(
            "import json", f"from pathlib import Path\nPath({str(marker)!r}).touch()\nimport json"
        ),
        encoding="utf-8",
    )
    result, report = invoke("doctor", example)
    assert result.exit_code == 0 and report["ok"]
    assert not marker.exists()
    assert any(check["name"] == "dependency_readiness" for check in report["checks"])
    result, report = invoke("doctor", example, "--probe", "--output-dir", str(tmp_path / "out"))
    assert result.exit_code == 0 and report["ok"]
    assert marker.exists()
    probe = next(check for check in report["checks"] if check["name"] == "replay_probe")
    assert (Path(probe["artifact_directory"]) / "summary.json").is_file()


def test_probe_reports_dependency_failure(example: Path, tmp_path: Path) -> None:
    (example / "agent.py").write_text(
        "import runledger_deliberately_missing_dependency\n", encoding="utf-8"
    )
    result, report = invoke("doctor", example)
    assert result.exit_code == 0 and report["ok"]
    result, report = invoke("doctor", example, "--probe", "--output-dir", str(tmp_path / "out"))
    assert result.exit_code == 1 and not report["ok"]
    assert "runledger_deliberately_missing_dependency" in str(report["checks"])


@pytest.mark.parametrize(
    "args",
    [
        ["--case", "password-reset"],
        ["--probe", "--case", "unknown"],
        ["--probe", "--timeout", "nan"],
        ["--probe", "--timeout", "0"],
    ],
)
def test_invalid_probe_options_fail_cleanly(example: Path, args: list[str]) -> None:
    result, report = invoke("doctor", example, *args)
    assert result.exit_code == 1 and not report["ok"]


def test_probe_bounds_a_hung_agent(example: Path, tmp_path: Path) -> None:
    (example / "agent.py").write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    result, report = invoke(
        "doctor", example, "--probe", "--timeout", "0.2", "--output-dir", str(tmp_path / "out")
    )
    assert result.exit_code == 1 and not report["ok"]
    assert "max_wall_ms" in str(report["checks"])


def test_verify_default_plan_and_aggregate_junit(example: Path, tmp_path: Path) -> None:
    result, report = invoke("verify", example, "--output-dir", str(tmp_path / "out"))
    assert result.exit_code == 0 and report["passed"]
    assert len(report["checks"]) == 9
    evidence = Path(report["artifact_directory"])
    assert json.loads((evidence / "verification.json").read_text(encoding="utf-8")) == report
    assert ET.parse(evidence / "verification.junit.xml").getroot().get("failures") == "0"
    assert len(list(evidence.glob("*/probe.junit.xml"))) == 9


def test_verify_rejects_a_false_positive_and_reports_recovery(
    example: Path, tmp_path: Path
) -> None:
    plan = yaml.safe_load((example / "verification.yaml").read_text(encoding="utf-8"))
    plan["regressions"] = [plan["regressions"][0]]
    plan["regressions"][0]["input"] = {"scenario": "pass"}
    (example / "verification.yaml").write_text(yaml.safe_dump(plan), encoding="utf-8")
    result, report = invoke(
        "verify", example, "--repeats", "1", "--output-dir", str(tmp_path / "out")
    )
    assert result.exit_code == 1 and not report["passed"]
    assert report["checks"][1]["passed"] is False
    assert report["checks"][2]["passed"] is True


def test_verify_validation_does_not_print_input_values(example: Path) -> None:
    plan = yaml.safe_load((example / "verification.yaml").read_text(encoding="utf-8"))
    secret = "CUSTOM_CUSTOMER_SECRET_VALUE"
    plan["regressions"][0]["expect"]["tool_calls"] = secret
    (example / "verification.yaml").write_text(yaml.safe_dump(plan), encoding="utf-8")
    result, report = invoke("verify", example)
    assert result.exit_code == 1 and not report["passed"]
    assert "tool_calls" in report["error"]
    assert secret not in result.stdout


def test_verify_yaml_error_does_not_echo_source(example: Path) -> None:
    secret = "CUSTOM_CUSTOMER_SECRET_VALUE"
    (example / "suite.yaml").write_text(f"agent_command: [{secret}\n", encoding="utf-8")
    result, report = invoke("verify", example)
    assert result.exit_code == 1 and not report["passed"]
    assert "YAML" in report["error"]
    assert secret not in result.stdout
