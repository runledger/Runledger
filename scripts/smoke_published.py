"""Verify a published RunLedger version from a temporary, clean installation."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import venv
import xml.etree.ElementTree as ET
from pathlib import Path


def execute(command, *, cwd, env, timeout=120):
    return subprocess.run(
        [str(part) for part in command],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command_error(result):
    return (result.stdout + "\n" + result.stderr).strip()[-4000:]


def validate_artifacts(output_dir, *, passed, missing_field=None, junit_name="junit.xml"):
    summaries = list(output_dir.rglob("summary.json"))
    require(
        len(summaries) == 1, f"Expected one summary under {output_dir.name}, got {len(summaries)}"
    )
    run_dir = summaries[0].parent
    for name in ("summary.json", "run.jsonl", junit_name, "report.html"):
        path = run_dir / name
        require(path.is_file() and path.stat().st_size > 0, f"Missing or empty artifact: {name}")
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    cases = summary.get("cases", [])
    require(bool(cases), "Run produced no cases")
    status = summary.get("run", {}).get("exit_status")
    require((status == "success") == passed, f"Unexpected summary status: {status}")
    failures = ET.parse(run_dir / junit_name).findall(".//failure")
    errors = ET.parse(run_dir / junit_name).findall(".//error")
    require(bool(failures or errors) != passed, "JUnit disagrees with the expected run outcome")
    events = [
        json.loads(line)
        for line in (run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    require(bool(events), "Run log has no events")
    require(any(event.get("type") == "case_end" for event in events), "Run log has no case_end")
    if missing_field is not None:
        require(
            any(missing_field in str(case.get("failure_reason", "")) for case in cases),
            "Deliberate schema failure did not name the missing field",
        )
    return {"cases": len(cases), "exit_status": status, "artifacts_checked": 4}


def validate_verification(report, output_dir):
    require(report.get("passed") is True, "Verification did not pass")
    directory = Path(report["artifact_directory"])
    require(
        directory.resolve().is_relative_to(output_dir.resolve()),
        "Unexpected verification artifact directory",
    )
    require(
        json.loads((directory / "verification.json").read_text(encoding="utf-8")) == report,
        "Persisted verification JSON differs from CLI JSON",
    )
    regressions = [
        ("missing-field", "assertion_failed", "json_schema", 1),
        ("skipped-lookup", "assertion_failed", "must_call", 0),
        ("excess-tool-call", "budget_exceeded", "max_tool_calls", 2),
    ]
    names = [f"unchanged-{number:02}" for number in range(1, 4)]
    for number, (name, *_rest) in enumerate(regressions, 1):
        names.extend([f"regression-{number:02}-{name}", f"recovery-{number:02}-{name}"])
    checks = report.get("checks", [])
    require(
        [check.get("name") for check in checks] == names,
        "Expected exactly nine ordered verification checks",
    )
    require(all(check.get("passed") is True for check in checks), "A verification check failed")
    fingerprints = checks[0].get("behavior_sha256", [])
    require(
        isinstance(fingerprints, list)
        and len(fingerprints) == 1
        and fingerprints[0].get("case_id") == "password-reset",
        "Missing known-good behavior fingerprint",
    )
    digest = fingerprints[0].get("sha256")
    require(
        isinstance(digest, str)
        and len(digest) == 64
        and all(c in "0123456789abcdef" for c in digest),
        "Invalid SHA256 behavior fingerprint",
    )
    by_name = {check["name"]: check for check in checks}
    for name in names:
        check = by_name[name]
        require(check.get("artifacts") == name, f"Unexpected artifact path for {name}")
        good = not name.startswith("regression-")
        evidence = validate_artifacts(directory / name, passed=good, junit_name="probe.junit.xml")
        require(evidence["cases"] == 1, f"Expected one case in {name}")
        if good:
            require(
                check.get("behavior_sha256") == fingerprints,
                f"Behavior fingerprint changed in {name}",
            )

    for number, (name, failure_type, failure_field, calls) in enumerate(regressions, 1):
        key = f"regression-{number:02}-{name}"
        check = by_name[key]
        require(
            check.get("actual_failure_type") == failure_type and check.get("tool_calls") == calls,
            f"Wrong negative result for {name}",
        )
        events = [
            json.loads(line)
            for line in (directory / key / "run.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        failures = [
            failure
            for event in events
            if event.get("type") in {"assertion_failure", "budget_failure"}
            for failure in event["failures"]
        ]
        require(len(failures) == 1, f"Expected exactly one intended failure for {name}")
        field = "type" if failure_type == "assertion_failed" else "field"
        require(failures[0].get(field) == failure_field, f"Wrong raw failure for {name}")
        require(
            sum(event.get("type") == "tool_call" for event in events) == calls,
            f"Wrong raw tool count for {name}",
        )
        if name == "missing-field":
            require(
                "reply" in failures[0].get("message", ""),
                "Schema regression did not identify reply",
            )
        elif name == "skipped-lookup":
            require(
                failures[0].get("details", {}).get("missing") == ["search_docs"],
                "Contract regression did not identify search_docs",
            )
        else:
            require(
                failures[0].get("limit") == 1 and failures[0].get("actual") == 2,
                "Budget regression did not identify the excess tool call",
            )

    junit = ET.parse(directory / "verification.junit.xml").getroot()
    require(
        junit.get("tests") == "9" and junit.get("failures") == "0", "Wrong aggregate JUnit counts"
    )
    require(
        len(junit.findall("testcase")) == 9
        and not junit.findall(".//failure")
        and not junit.findall(".//error"),
        "Aggregate JUnit must contain nine passing checks",
    )
    return {
        "aggregate_checks": 9,
        "deliberate_regressions": 3,
        "behavior_sha256": fingerprints,
        "artifacts_checked": 38,
    }


def check_doctor_and_verify(python, *, project, env, result):
    source = Path(__file__).resolve().parents[1] / "examples" / "verification"
    suite = project / "verification"
    shutil.copytree(source, suite, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for probe in (False, True):
        name = "doctor_probe" if probe else "doctor_static"
        print(f"Checking {name}", file=sys.stderr, flush=True)
        command = [python, "-I", "-m", "runledger", "doctor", suite, "--json"]
        if probe:
            command.extend(
                ["--probe", "--case", "password-reset", "--output-dir", project / "doctor_out"]
            )
        completed = execute(command, cwd=project, env=env)
        require(completed.returncode == 0, f"{name} failed:\n" + command_error(completed))
        report = json.loads(completed.stdout)
        require(report.get("ok") is True, f"{name} JSON did not report success")
        probes = [
            check for check in report.get("checks", []) if check.get("name") == "replay_probe"
        ]
        evidence = {}
        if probe:
            require(
                len(probes) == 1 and probes[0].get("status") == "pass",
                "Doctor replay probe did not pass",
            )
            evidence = validate_artifacts(
                Path(probes[0]["artifact_directory"]), passed=True, junit_name="probe.junit.xml"
            )
        else:
            require(not probes, "Static doctor unexpectedly reported an execution probe")
        result["checks"].append(
            {"name": name, "passed": True, "exit_code": completed.returncode, **evidence}
        )

    print("Checking generic verification", file=sys.stderr, flush=True)
    output = project / "verify_out"
    completed = execute(
        [
            python,
            "-I",
            "-m",
            "runledger",
            "verify",
            suite,
            "--repeats",
            "3",
            "--output-dir",
            output,
            "--json",
        ],
        cwd=project,
        env=env,
    )
    require(completed.returncode == 0, "Generic verification failed:\n" + command_error(completed))
    evidence = validate_verification(json.loads(completed.stdout), output)
    result["checks"].append(
        {
            "name": "generic_verification",
            "passed": True,
            "exit_code": completed.returncode,
            **evidence,
        }
    )


def smoke(version, *, attempts, retry_delay, result, wheel=None):
    with tempfile.TemporaryDirectory(prefix="runledger-published-smoke-") as scratch:
        root = Path(scratch)
        environment = root / "venv"
        project = root / "project"
        project.mkdir()
        print("Creating clean virtual environment", file=sys.stderr, flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        env = dict(os.environ)
        for name in (
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
            "PIP_USER",
            "PIP_TARGET",
            "PIP_PREFIX",
        ):
            env.pop(name, None)
        env["VIRTUAL_ENV"] = str(environment)
        env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONNOUSERSITE"] = "1"

        install = None
        for attempt in range(1, attempts + 1):
            package = str(wheel) if wheel is not None else f"runledger=={version}"
            print(
                f"Installing {package}, attempt {attempt}/{attempts}", file=sys.stderr, flush=True
            )
            try:
                install = execute(
                    [
                        python,
                        "-I",
                        "-m",
                        "pip",
                        "--isolated",
                        "install",
                        "--disable-pip-version-check",
                        "--no-input",
                        "--no-cache-dir",
                        "--index-url",
                        "https://pypi.org/simple",
                        package,
                    ],
                    cwd=project,
                    env=env,
                )
                if install.returncode == 0:
                    break
                detail = command_error(install)
            except subprocess.TimeoutExpired:
                detail = "pip install exceeded the 120-second attempt timeout"
            if attempt == attempts:
                raise RuntimeError(
                    f"Published package installation failed after {attempts} attempts:\n{detail}"
                )
            print(f"Install not ready; retrying in {retry_delay:g}s", file=sys.stderr, flush=True)
            time.sleep(retry_delay)

        probe = execute(
            [
                python,
                "-I",
                "-c",
                (
                    "import json, sys, runledger; from importlib.metadata import version; "
                    "print(json.dumps({'module':runledger.__file__,'prefix':sys.prefix,"
                    "'metadata_version':version('runledger'),'module_version':runledger.__version__}))"
                ),
            ],
            cwd=project,
            env=env,
            timeout=30,
        )
        require(probe.returncode == 0, "Installed import failed:\n" + command_error(probe))
        installed = json.loads(probe.stdout)
        require(installed["metadata_version"] == version, f"Wrong installed version: {installed}")
        require(installed["module_version"] == version, f"Wrong module version: {installed}")
        require(
            Path(installed["prefix"]).resolve() == environment.resolve(),
            "Python did not use the clean environment",
        )
        require(
            Path(installed["module"]).resolve().is_relative_to(environment.resolve()),
            "Imported source outside the clean environment",
        )
        result["checks"].append(
            {"name": "clean_install", "version": version, "attempts": attempt, "passed": True}
        )

        print("Running README init", file=sys.stderr, flush=True)
        initialized = execute([python, "-I", "-m", "runledger", "init"], cwd=project, env=env)
        require(initialized.returncode == 0, "README init failed:\n" + command_error(initialized))
        require((project / "baselines" / "demo.json").is_file(), "Init did not create its baseline")
        result["checks"].append({"name": "readme_init", "passed": True})

        def run(name, mode, *, passed=True, missing_field=None):
            print(f"Checking {name}", file=sys.stderr, flush=True)
            output = project / "smoke_out" / name
            run_result = execute(
                [
                    python,
                    "-I",
                    "-m",
                    "runledger",
                    "run",
                    "evals/demo",
                    "--mode",
                    mode,
                    "--baseline",
                    "baselines/demo.json",
                    "--output-dir",
                    output,
                ],
                cwd=project,
                env=env,
            )
            require(
                (run_result.returncode == 0) == passed,
                f"{name} returned {run_result.returncode}, expected {'zero' if passed else 'nonzero'}:\n"
                + command_error(run_result),
            )
            evidence = validate_artifacts(output, passed=passed, missing_field=missing_field)
            result["checks"].append(
                {"name": name, "passed": True, "exit_code": run_result.returncode, **evidence}
            )

        run("readme_replay", "replay")
        run("record", "record")
        run("recorded_replay", "replay")
        schema_path = project / "evals" / "demo" / "schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        missing_field = "published_smoke_missing_field"
        schema.setdefault("required", []).append(missing_field)
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        run("intentional_schema_failure", "replay", passed=False, missing_field=missing_field)
        check_doctor_and_verify(python, project=project, env=env, result=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", required=True, help="Exact PyPI version to verify, for example 0.2.5"
    )
    parser.add_argument(
        "--wheel",
        type=Path,
        help="Validate this local wheel before publishing instead of installing from PyPI",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=5,
        help="Bounded installation attempts for registry propagation",
    )
    parser.add_argument(
        "--retry-delay", type=float, default=10, help="Seconds between install attempts"
    )
    args = parser.parse_args()
    if not 1 <= args.attempts <= 10 or not 0 <= args.retry_delay <= 30:
        parser.error("--attempts must be 1..10 and --retry-delay must be 0..30")
    if args.wheel is not None:
        args.wheel = args.wheel.resolve()
        if not args.wheel.is_file() or args.wheel.suffix != ".whl":
            parser.error("--wheel must identify an existing .whl file")
    started = time.monotonic()
    result = {
        "ok": False,
        "requested_version": args.version,
        "python": platform.python_version(),
        "platform": platform.system(),
        "installation_source": "local_wheel" if args.wheel else "pypi",
        "checks": [],
    }
    try:
        smoke(
            args.version,
            attempts=args.attempts,
            retry_delay=args.retry_delay,
            result=result,
            wheel=args.wheel,
        )
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001 - Emit a JSON failure for every smoke error.
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
