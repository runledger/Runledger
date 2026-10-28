"""The public download must execute in isolation, without the installed project."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "templates" / "support-agent"


def test_pack_matches_source_and_published_evidence():
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_text_normalization"] == "lf"
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((PACK / name).read_bytes()).hexdigest() == expected, name
    for name, expected in manifest["sources"].items():
        assert hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected, name
    data = json.loads((PACK / "demo-results.json").read_text(encoding="utf-8"))
    assert data["simulator_sha256"] == manifest["simulator_sha256"]
    assert sum(not case["before"]["passed"] for case in data["scenarios"]) == 3
    assert all(case["after"]["passed"] for case in data["scenarios"])


def test_downloaded_pack_runs_without_site_packages_and_reproduces_incident(tmp_path):
    with zipfile.ZipFile(PACK / "runledger-support-agent.zip") as archive:
        assert all(not name.startswith("/") and ".." not in Path(name).parts for name in archive.namelist())
        archive.extractall(tmp_path)
    environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
    def execute(*args):
        return subprocess.run([sys.executable, "-S", "run_demo.py", *args], cwd=tmp_path,
                              env=environment, text=True, capture_output=True, timeout=30, check=False)
    verify = execute("verify", "--out", "results")
    assert verify.returncode == 0, verify.stdout + verify.stderr
    published = json.loads((PACK / "demo-results.json").read_text(encoding="utf-8"))
    actual = json.loads((tmp_path / "results" / "comparison.json").read_text(encoding="utf-8"))
    assert actual["scenarios"] == published["scenarios"]
    reproduce = execute("reproduce", "incident.json", "--out", "reproduced")
    assert reproduce.returncode == 0, reproduce.stdout + reproduce.stderr
    reproduction = json.loads((tmp_path / "reproduced" / "reproduction.json").read_text(encoding="utf-8"))
    assert reproduction["matched"] is True
    assert reproduction["result"]["passed"] is False
    promote = execute("promote", "incident.json", "--to", "cases/refund.json")
    assert promote.returncode == 0, promote.stderr
    assert execute("run", "--case", "cases/refund.json", "--agent", "unsafe", "--out", "broken").returncode == 1
    assert execute("run", "--case", "cases/refund.json", "--agent", "fixed", "--out", "fixed").returncode == 0


def test_full_source_download_is_allowlisted_and_runs_custom_adapter(tmp_path):
    supporting = {"pyproject.toml", "README.md", "LICENSE", "MANIFEST.in", "CHANGELOG.md", "docs/support-agent-pack.md",
                  "docs/production-incidents.md", "examples/support-agent/agent.py",
                  "examples/support-agent/verify_adapter.py", "examples/incidents/production-example.json",
                  "examples/incidents/replay_agent.py", "examples/incidents/replay_example.py"}
    expected = {path.relative_to(ROOT).as_posix()
                for path in (ROOT / "src" / "runledger").rglob("*.py")
                if "__pycache__" not in path.parts} | supporting
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(PACK / "runledger-scenario-source.zip") as archive:
        assert set(archive.namelist()) == expected
        assert len(archive.namelist()) == len(expected), "No duplicate archive paths"
        for name in archive.namelist():
            parts = Path(name).parts
            assert not name.startswith("/") and ".." not in parts
            assert not any(part.startswith(".env") or part in {".git", ".vercel", "__pycache__"}
                           for part in parts)
            data = archive.read(name)
            assert data == (ROOT / name).read_bytes().replace(b"\r\n", b"\n"), name
            assert b"\r\n" not in data, name
            assert hashlib.sha256(data).hexdigest() == manifest["sources"][name], name
        assert b"runledger-scenario-source.zip" in archive.read("README.md")
        assert "src/runledger/scenarios/cli.py" in archive.namelist()
        assert "src/runledger/runner/subprocess.py" in archive.namelist()
        archive.extractall(tmp_path)

    # Use the test runtime's already installed dependencies without installing,
    # replacing, or importing the working checkout's RunLedger package.
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"PYTHONPATH", "PYTHONHOME"}}
    environment["PYTHONPATH"] = str(tmp_path / "src")

    def execute(*args):
        return subprocess.run([sys.executable, *args], cwd=tmp_path, env=environment,
                              text=True, capture_output=True, timeout=30, check=False)

    location = execute("-c", "import runledger; print(runledger.__file__)")
    assert location.returncode == 0, location.stderr
    assert Path(location.stdout.strip()).resolve() == (tmp_path / "src" / "runledger" / "__init__.py").resolve()
    help_result = execute("-m", "runledger", "scenario", "--help")
    assert help_result.returncode == 0, help_result.stderr
    assert "--agent-command" in execute("-m", "runledger", "scenario", "verify", "--help").stdout
    verified = execute("examples/support-agent/verify_adapter.py")
    assert verified.returncode == 0, verified.stdout + verified.stderr
    results = json.loads((tmp_path / "adapter-results" / "comparison.json").read_text(encoding="utf-8"))
    assert len(results["scenarios"]) == 5
    assert all(case["after"]["agent"] == "custom" and case["comparison"]["verified"]
               for case in results["scenarios"])
    assert (tmp_path / "adapter-results" / "report.html").is_file()
    assert not list((tmp_path / "adapter-results").glob("*/after/incident.json"))

    replayed = execute("examples/incidents/replay_example.py")
    assert replayed.returncode == 0, replayed.stdout + replayed.stderr
    replay_folder = tmp_path / "incident-example-replayed"
    replay = json.loads((replay_folder / "replay.json").read_text(encoding="utf-8"))
    evaluation = json.loads((replay_folder / "evaluation.json").read_text(encoding="utf-8"))
    assert replay["matched"] is True
    assert replay["observed"]["passed"] is False
    assert evaluation["passed"] is False
    assert len(evaluation["effects"]) == 2
    assert any(not rule["passed"] for rule in evaluation["assertions"])
    assert (replay_folder / "report.html").is_file()

    gated = execute("-m", "runledger", "incident", "replay",
                    "incident-example-imported/incident.json", "--agent-command",
                    json.dumps([sys.executable, str(tmp_path / "examples/incidents/replay_agent.py")]),
                    "--gate", "--out", "incident-example-gated")
    assert gated.returncode == 1, gated.stdout + gated.stderr
    gate = json.loads((tmp_path / "incident-example-gated/replay.json").read_text(encoding="utf-8"))
    assert gate["matched"] is True, "The gate must fail for the reproduced rule failure, not divergence"
