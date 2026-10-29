"""Capture an OpenChatBI graph regression and import it with the same explicit rule."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

import runledger
from runledger import __version__ as runledger_runtime_version
from runledger.config.loader import load_cases, load_suite
from runledger.incidents.importer import normalize_run_log
from runledger.incidents.schema import parse_json, read_bytes, validate_rules

HERE = Path(__file__).resolve().parent
CASE_ID = "c21_schema_discovery"
RULE = {"id": "schema-discovery", "type": "must_call", "tools": ["search_schema"]}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def save(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def package_source_provenance(module_file: Path) -> dict:
    """Identify the imported package source independently of editable metadata."""
    package = module_file.resolve().parent
    hashes = {}
    for path in sorted(package.rglob("*.py")):
        normalized = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        hashes[path.relative_to(package).as_posix()] = hashlib.sha256(normalized).hexdigest()
    require(bool(hashes), "Imported RunLedger package has no inspectable Python source")
    canonical = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "import_path": str(module_file.resolve()),
        "source_sha256": hashlib.sha256(canonical).hexdigest(),
        "python_files": len(hashes),
        "normalization": "LF source bytes; canonical JSON map of relative paths to SHA256",
    }


def runtime_environment(out: Path) -> dict[str, str]:
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "HOME",
        "USERPROFILE",
        "TMP",
        "TEMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
    }
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in allowed and key.upper() != "PATH"
    }
    inherited = next(
        (value for key, value in os.environ.items() if key.upper() == "PATH"), os.defpath
    )
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + inherited
    env.update(
        PYTHONIOENCODING="utf-8",
        PYTHONDONTWRITEBYTECODE="1",
        OPENCHATBI_TEST_MODE="true",
        CONFIG_FILE=str(out / "missing-openchatbi-config.yaml"),
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
    )
    return env


def validate_capture(path: Path, case_id: str = CASE_ID) -> dict:
    """Require runner boundaries, then use the existing serial JSONL importer."""
    raw = read_bytes(path)
    records = [parse_json(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    require(all(isinstance(item, dict) for item in records), "Trace must contain JSON objects")
    selected = [item for item in records if item.get("case_id") == case_id]
    require(
        bool(selected)
        and selected[0].get("type") == "task_start"
        and selected[-1].get("type") == "case_end",
        "Trace needs its task_start and case_end boundaries",
    )
    require(
        sum(item.get("type") == "task_start" for item in selected) == 1
        and sum(item.get("type") == "case_end" for item in selected) == 1,
        "Trace has duplicate run boundaries",
    )
    require(
        not any(item.get("type") == "business_effect" for item in selected),
        "This recipe has no provider effect ledger; do not add inferred effects",
    )
    incident = normalize_run_log(raw, case=case_id, rules=[RULE], effects_complete=False)
    require(
        incident["events"][-1]["type"] == "final_output",
        "Expected a completed graph output, not an agent error",
    )
    return {
        "events": len(incident["events"]),
        "tool_calls": sum(event["type"] == "tool_call" for event in incident["events"]),
        "responses": sum(event["type"] == "tool_result" for event in incident["events"]),
        "complete_serial_trace": True,
        "effects_complete": False,
    }


def validate_verification(report: dict) -> dict:
    names = ["unchanged-01", "unchanged-02", "regression-01-skip-schema", "recovery-01-skip-schema"]
    checks = report.get("checks", [])
    require(
        report.get("passed") is True
        and [item.get("name") for item in checks] == names
        and all(item.get("passed") is True for item in checks),
        "Generic verification did not pass all four expected checks",
    )
    fingerprints = checks[0].get("behavior_sha256")
    require(
        isinstance(fingerprints, list)
        and len(fingerprints) == 1
        and fingerprints[0].get("case_id") == CASE_ID,
        "Missing original behavior fingerprint",
    )
    digest = fingerprints[0].get("sha256")
    require(
        isinstance(digest, str)
        and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest),
        "Invalid behavior fingerprint",
    )
    require(
        checks[1].get("behavior_sha256") == fingerprints
        and checks[3].get("behavior_sha256") == fingerprints,
        "Original and recovered behavior differ",
    )
    require(
        checks[2].get("actual_failure_type") == "assertion_failed"
        and checks[2].get("tool_calls") == 0,
        "Negative probe failed for an unrelated reason",
    )
    return {"aggregate_checks": 4, "unchanged_replays": 2, "original_and_recovery_sha256": digest}


def prepare_suite(repo: Path, out: Path) -> tuple[Path, list[Path]]:
    source = repo / "evals/runledger"
    suite = load_suite(source)
    selected = [case for case in load_cases(source, suite.cases_path) if case.id == CASE_ID]
    require(len(selected) == 1, "OpenChatBI must contain exactly one c21_schema_discovery case")
    case = selected[0]
    directory = out / "private-suite"
    (directory / "cases").mkdir(parents=True)
    (out / "runtime-receipts").mkdir()
    bridge = out / "adapter_bridge.py"
    shutil.copyfile(HERE / "adapter_bridge.py", bridge)
    command = [
        sys.executable,
        str(bridge),
        "--repo-dir",
        str(repo),
        "--receipts",
        str(out / "runtime-receipts"),
    ]
    data = suite.model_dump(exclude_none=True)
    data.update(agent_command=command, mode="replay", cases_path="cases")
    for field in ("baseline_path", "regression", "output_dir"):
        data.pop(field, None)
    case_data = case.model_dump(exclude_none=True)
    assertions = case_data.setdefault("assertions", [])
    if not any(
        item.get("type") == "must_call" and item.get("tools") == ["search_schema"]
        for item in data.get("assertions", []) + assertions
    ):
        assertions.append({"type": "must_call", "tools": ["search_schema"]})
    tracked = [
        source / "suite.yaml",
        source / "cases/c21_schema_discovery.yaml",
        Path(case.cassette),
        source / "agent/agent.py",
        repo / "openchatbi/agent_graph.py",
    ]
    for index, assertion in enumerate(data.get("assertions", []) + assertions):
        if assertion.get("type") == "json_schema":
            schema = Path(assertion["schema_path"])
            tracked.append(schema)
            copied = directory / f"schema-{index}.json"
            shutil.copyfile(schema, copied)
            assertion["schema_path"] = copied.name
    shutil.copyfile(case.cassette, directory / "cassette.jsonl")
    case_data["cassette"] = "cassette.jsonl"
    (directory / "suite.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    (directory / "cases/c21.yaml").write_text(
        yaml.safe_dump(case_data, sort_keys=False), encoding="utf-8"
    )
    plan = {
        "schema_version": 1,
        "regressions": [
            {
                "name": "skip-schema",
                "case_id": CASE_ID,
                "agent_command": command + ["--skip-schema"],
                "expect": {
                    "assertion": "must_call",
                    "details": {"missing": ["search_schema"]},
                    "tool_calls": 0,
                },
            }
        ],
    }
    (directory / "verification.yaml").write_text(
        yaml.safe_dump(plan, sort_keys=False), encoding="utf-8"
    )
    return directory, tracked


def capture(repo: Path, out: Path) -> dict:
    started = time.monotonic()
    runtime_source = package_source_provenance(Path(runledger.__file__))
    require(sys.version_info >= (3, 11), "OpenChatBI requires Python 3.11 or later")
    # Feature check before executing any application: v0.3.0 alone lacks this rule.
    validate_rules([RULE])
    require(
        not out.exists(), "Choose a new output directory; existing evidence is never overwritten"
    )
    require(
        (repo / "openchatbi/agent_graph.py").is_file(), "--repo-dir must be an OpenChatBI checkout"
    )
    revision = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    )
    out.mkdir(parents=True)
    suite, sources = prepare_suite(repo, out)
    source_hashes = {
        path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sources
    }
    save(out / "rules.json", [RULE])
    env = runtime_environment(out)
    commands = []

    def execute(name: str, arguments: list[str], expected: int = 0) -> subprocess.CompletedProcess:
        command = [sys.executable, "-m", "runledger", *arguments]
        result = subprocess.run(
            command,
            cwd=repo,
            env=env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=180,
            check=False,
        )
        (out / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (out / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        commands.append({"step": name, "argv": command, "exit_code": result.returncode})
        save(out / "commands.json", commands)
        require(
            result.returncode == expected,
            f"{name} returned {result.returncode}; inspect its local console files",
        )
        return result

    result = execute(
        "verify",
        [
            "verify",
            str(suite),
            "--repeats",
            "2",
            "--output-dir",
            str(out / "verification"),
            "--json",
        ],
    )
    report = json.loads(result.stdout)
    verified = validate_verification(report)
    artifacts = Path(report["artifact_directory"])
    imported = {}
    for label, stage, expected_calls, gate in [
        ("before", "regression-01-skip-schema", 0, 1),
        ("after", "recovery-01-skip-schema", 1, 0),
    ]:
        trace = artifacts / stage / "run.jsonl"
        complete = validate_capture(trace)
        require(complete["tool_calls"] == expected_calls, f"Unexpected tool trace in {label}")
        destination = out / "incidents" / label
        execute(
            f"import-{label}",
            [
                "incident",
                "import",
                str(trace),
                "--format",
                "runledger",
                "--case",
                CASE_ID,
                "--rules",
                str(out / "rules.json"),
                "--out",
                str(destination),
            ],
        )
        execute(
            f"inspect-{label}",
            [
                "incident",
                "inspect",
                str(destination / "incident.json"),
                "--gate",
                "--out",
                str(out / "gates" / label),
            ],
            expected=gate,
        )
        bundle = json.loads((destination / "incident.json").read_text(encoding="utf-8"))
        evaluation = json.loads((destination / "evaluation.json").read_text(encoding="utf-8"))
        require(bundle["incident"]["assertions"] == [RULE], "Imported rule changed")
        require(
            bundle["incident"]["effects_complete"] is False and evaluation["effects"] == [],
            "This recipe must not claim a complete provider effect ledger",
        )
        require(evaluation["passed"] is (gate == 0), f"Unexpected imported outcome in {label}")
        imported[label] = {
            **complete,
            "gate_exit_code": gate,
            "passed": evaluation["passed"],
            "incident": (destination / "incident.json").relative_to(out).as_posix(),
        }
    receipts = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (out / "runtime-receipts").glob("*.json")
    ]
    require(
        len(receipts) == 4
        and sum(item["scenario"] == "skip-schema" for item in receipts) == 1
        and all(item["graph_builds"] == item["graph_invocations"] == 1 for item in receipts),
        "Missing evidence that all four probes built and invoked the actual graph",
    )
    require(
        all(
            hashlib.sha256(path.read_bytes()).hexdigest()
            == source_hashes[path.relative_to(repo).as_posix()]
            for path in sources
        ),
        "Source checkout changed during capture",
    )
    require(
        package_source_provenance(Path(runledger.__file__)) == runtime_source,
        "RunLedger package source changed during capture",
    )
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    manifest.update(
        source_revision=revision,
        source_git_dirty=dirty,
        source_sha256=source_hashes,
        source_hash_scope="Selected suite, case, cassette, schemas, adapter, and graph files; not the entire checkout.",
        runledger_runtime_version=runledger_runtime_version,
        runledger_runtime_source=runtime_source,
        installed_packages={
            name: importlib.metadata.version(name)
            for name in ("runledger", "openchatbi", "langgraph")
        },
    )
    save(out / "manifest.json", manifest)
    acceptance = {
        "passed": True,
        "case_id": CASE_ID,
        "rule": RULE,
        **verified,
        "captures": imported,
        "real_graph_invocations": len(receipts),
        "effects_complete": False,
        "review_required": True,
        "source_files_unchanged": True,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "verification_json": (artifacts / "verification.json").relative_to(out).as_posix(),
    }
    save(out / "acceptance.json", acceptance)
    return acceptance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = capture(args.repo_dir.resolve(), args.out.resolve())
    except (ValueError, OSError, KeyError, ImportError, subprocess.SubprocessError) as exc:
        print(f"Handoff failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
