"""Verify a published RunLedger version from a temporary, clean installation."""
from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import venv
import xml.etree.ElementTree as ET


def execute(command, *, cwd, env, timeout=120):
    return subprocess.run(
        [str(part) for part in command], cwd=cwd, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command_error(result):
    return (result.stdout + "\n" + result.stderr).strip()[-4000:]


def validate_artifacts(output_dir, *, passed, missing_field=None):
    summaries = list(output_dir.rglob("summary.json"))
    require(len(summaries) == 1, f"Expected one summary under {output_dir.name}, got {len(summaries)}")
    run_dir = summaries[0].parent
    for name in ("summary.json", "run.jsonl", "junit.xml", "report.html"):
        path = run_dir / name
        require(path.is_file() and path.stat().st_size > 0, f"Missing or empty artifact: {name}")
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    cases = summary.get("cases", [])
    require(bool(cases), "Run produced no cases")
    status = summary.get("run", {}).get("exit_status")
    require((status == "success") == passed, f"Unexpected summary status: {status}")
    failures = ET.parse(run_dir / "junit.xml").findall(".//failure")
    errors = ET.parse(run_dir / "junit.xml").findall(".//error")
    require(bool(failures or errors) != passed, "JUnit disagrees with the expected run outcome")
    events = [json.loads(line) for line in (run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    require(bool(events), "Run log has no events")
    require(any(event.get("type") == "case_end" for event in events), "Run log has no case_end")
    if missing_field is not None:
        require(
            any(missing_field in str(case.get("failure_reason", "")) for case in cases),
            "Deliberate schema failure did not name the missing field",
        )
    return {"cases": len(cases), "exit_status": status, "artifacts_checked": 4}


def smoke(version, *, attempts, retry_delay, result):
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
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PIP_USER", "PIP_TARGET", "PIP_PREFIX"):
            env.pop(name, None)
        env["VIRTUAL_ENV"] = str(environment)
        env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONNOUSERSITE"] = "1"

        install = None
        for attempt in range(1, attempts + 1):
            print(f"Installing runledger=={version}, attempt {attempt}/{attempts}", file=sys.stderr, flush=True)
            try:
                install = execute(
                    [python, "-I", "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
                     "--no-input", "--no-cache-dir", "--index-url", "https://pypi.org/simple",
                     f"runledger=={version}"],
                    cwd=project, env=env,
                )
                if install.returncode == 0:
                    break
                detail = command_error(install)
            except subprocess.TimeoutExpired:
                detail = "pip install exceeded the 120-second attempt timeout"
            if attempt == attempts:
                raise RuntimeError(f"Published package installation failed after {attempts} attempts:\n{detail}")
            print(f"Install not ready; retrying in {retry_delay:g}s", file=sys.stderr, flush=True)
            time.sleep(retry_delay)

        probe = execute(
            [python, "-I", "-c",
             "import json, sys, runledger; from importlib.metadata import version; "
             "print(json.dumps({'module':runledger.__file__,'prefix':sys.prefix,"
             "'metadata_version':version('runledger'),'module_version':runledger.__version__}))"],
            cwd=project, env=env, timeout=30,
        )
        require(probe.returncode == 0, "Installed import failed:\n" + command_error(probe))
        installed = json.loads(probe.stdout)
        require(installed["metadata_version"] == version, f"Wrong installed version: {installed}")
        require(installed["module_version"] == version, f"Wrong module version: {installed}")
        require(Path(installed["prefix"]).resolve() == environment.resolve(), "Python did not use the clean environment")
        require(Path(installed["module"]).resolve().is_relative_to(environment.resolve()), "Imported source outside the clean environment")
        result["checks"].append({"name": "clean_install", "version": version, "attempts": attempt, "passed": True})

        print("Running README init", file=sys.stderr, flush=True)
        initialized = execute([python, "-I", "-m", "runledger", "init"], cwd=project, env=env)
        require(initialized.returncode == 0, "README init failed:\n" + command_error(initialized))
        require((project / "baselines" / "demo.json").is_file(), "Init did not create its baseline")
        result["checks"].append({"name": "readme_init", "passed": True})

        def run(name, mode, *, passed=True, missing_field=None):
            print(f"Checking {name}", file=sys.stderr, flush=True)
            output = project / "smoke_out" / name
            run_result = execute(
                [python, "-I", "-m", "runledger", "run", "evals/demo", "--mode", mode,
                 "--baseline", "baselines/demo.json", "--output-dir", output],
                cwd=project, env=env,
            )
            require(
                (run_result.returncode == 0) == passed,
                f"{name} returned {run_result.returncode}, expected {'zero' if passed else 'nonzero'}:\n" + command_error(run_result),
            )
            evidence = validate_artifacts(output, passed=passed, missing_field=missing_field)
            result["checks"].append({"name": name, "passed": True, "exit_code": run_result.returncode, **evidence})

        run("readme_replay", "replay")
        run("record", "record")
        run("recorded_replay", "replay")
        schema_path = project / "evals" / "demo" / "schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        missing_field = "published_smoke_missing_field"
        schema.setdefault("required", []).append(missing_field)
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        run("intentional_schema_failure", "replay", passed=False, missing_field=missing_field)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Exact PyPI version to verify, for example 0.2.4")
    parser.add_argument("--attempts", type=int, default=5, help="Bounded installation attempts for registry propagation")
    parser.add_argument("--retry-delay", type=float, default=10, help="Seconds between install attempts")
    args = parser.parse_args()
    if not 1 <= args.attempts <= 10 or not 0 <= args.retry_delay <= 30:
        parser.error("--attempts must be 1..10 and --retry-delay must be 0..30")
    started = time.monotonic()
    result = {"ok": False, "requested_version": args.version, "python": platform.python_version(),
              "platform": platform.system(), "checks": []}
    try:
        smoke(args.version, attempts=args.attempts, retry_delay=args.retry_delay, result=result)
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
