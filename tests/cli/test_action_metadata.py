from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_action_metadata_is_marketplace_ready() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert action["name"] == "RunLedger"
    assert action["branding"]["icon"] == "check-circle"
    assert action["branding"]["color"] == "blue"
    assert action["runs"]["using"] == "composite"
    assert action["inputs"]["path"]["default"] == "./evals/demo"
    assert action["inputs"]["baseline"]["default"] == ""
    for key in ("result", "exit-code", "artifacts-path"):
        assert action["outputs"][key]["description"]
        assert action["outputs"][key]["value"].startswith("${{ steps.run.outputs.")
    description = action["description"]
    assert "token" not in description.lower()
    assert "cost" not in description.lower()
    assert len(description) <= 125


def test_action_self_test_uses_local_action() -> None:
    workflow = (ROOT / ".github" / "workflows" / "action-self-test.yml").read_text(encoding="utf-8")
    assert "uses: ./" in workflow
    assert "examples/evals/demo" in workflow
    assert "baselines/demo.json" in workflow


def test_artifact_path_output_strips_glob() -> None:
    script = r"""
artifacts="$1"
artifacts="${artifacts//$'\n'/}"
artifacts="${artifacts//$'\r'/}"
while true; do
  case "${artifacts}" in
    */) artifacts="${artifacts%/}" ;;
    *'/**') artifacts="${artifacts%'/**'}" ;;
    *) break ;;
  esac
done
if [ -z "${artifacts}" ]; then
  artifacts=runledger_out
fi
printf '%s' "${artifacts}"
"""
    cases = {
        "runledger_out/**": "runledger_out",
        "runledger_out/**/": "runledger_out",
        "custom/out": "custom/out",
        "": "runledger_out",
    }
    for raw, expected in cases.items():
        result = subprocess.run(
            ["bash", "-c", script, "bash", raw],
            text=True,
            capture_output=True,
            check=True,
        )
        assert result.stdout == expected
