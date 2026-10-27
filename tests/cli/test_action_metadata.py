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


def test_action_records_outputs_before_failing_the_job() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    steps = action["runs"]["steps"]
    run_step = next(step for step in steps if step.get("id") == "run")
    assert 'exit "${code}"' not in run_step["run"]
    fail_step = next(step for step in steps if "exit-code" in str(step.get("if", "")))
    assert fail_step["if"] == "steps.run.outputs.exit-code != '0'"
    assert steps.index(fail_step) > steps.index(run_step)
    upload_step = next(step for step in steps if step.get("uses", "").startswith("actions/upload-artifact"))
    assert steps.index(upload_step) < steps.index(fail_step)


def test_readme_pins_the_released_action() -> None:
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    ci = (ROOT / "docs" / "ci.md").read_text(encoding="utf-8")
    site = (ROOT / "docs" / "site-quickstart.md").read_text(encoding="utf-8")
    for text in (readme, ci, site):
        assert "runledger/Runledger@v0.2.3" in text
        assert re.search(r"runledger/Runledger@v0\.2(?!\.)", text) is None


def test_release_workflow_publishes_the_tagged_version() -> None:
    import runledger

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.2.3"' in pyproject
    assert runledger.__version__ == "0.2.3"
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
    # PyYAML 1.1 parses the unquoted workflow key "on" as boolean true.
    assert workflow[True]["push"]["tags"] == ["v*"]
    steps = workflow["jobs"]["publish"]["steps"]
    gate = next(step for step in steps if step.get("name") == "Require the tag to match the package version")
    build = next(step for step in steps if step.get("name") == "Build")
    publish = next(step for step in steps if step.get("name") == "Publish to PyPI")
    assert steps.index(gate) < steps.index(build) < steps.index(publish)
    assert 'version="${tag#v}"' in gate["run"]
    assert "[ \"$package\" != \"$version\" ]" in gate["run"]
    assert "python -m build" in build["run"]
    assert publish["uses"] == "pypa/gh-action-pypi-publish@release/v1"


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
