"""Portable, data-only evidence for the built-in synthetic support scenarios.

Version 1 deliberately accepts only the shipped fixtures and deterministic demo
agents. It is not a redactor or an export format for real customer incidents.
Nothing in an imported bundle is treated as a command, path, or Python code.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MAX_BUNDLE_BYTES = 2 * 1024 * 1024
_KIND = "runledger.synthetic-incident"
_AGENTS = {"unsafe", "fixed"}
_SOURCE_FILES = ("core.py", "agents.py", "pack.py")
_BOUNDARY = {
    "environment": "local synthetic support simulator",
    "inputs": "versioned built-in synthetic fixtures only",
    "tools": "simulated orders, approvals, and refunds",
    "agent": "built-in deterministic action policy",
    "live_models": False,
    "live_payments": False,
    "external_network": False,
    "customer_data": False,
    "automatic_redaction": False,
}
_FIELDS = {
    "schema_version", "kind", "synthetic_only", "scenario", "agent",
    "observed_result", "fingerprints", "boundary",
}
_HASH_FIELDS = {"scenario_sha256", "result_sha256", "simulator_sha256"}


class BundleError(ValueError):
    """The bundle cannot be safely interpreted by this simulator version."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise BundleError("Bundle values must be finite, JSON-compatible data") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def simulator_fingerprint() -> str:
    """Hash packaged simulator sources with CRLF normalized to LF for portability."""
    digest = hashlib.sha256()
    directory = Path(__file__).resolve().parent
    for filename in _SOURCE_FILES:
        try:
            source = (directory / filename).read_bytes().replace(b"\r\n", b"\n")
        except OSError as exc:
            raise BundleError(f"Simulator source is unavailable: {filename}") from exc
        digest.update(filename.encode("ascii") + b"\0")
        digest.update(len(source).to_bytes(8, "big"))
        digest.update(source)
    return digest.hexdigest()


def _canonical_scenario(spec: Any) -> dict[str, Any]:
    from .pack import get_scenario

    if not isinstance(spec, dict) or not isinstance(spec.get("id"), str):
        raise BundleError("Bundle scenario must be a built-in synthetic fixture")
    try:
        canonical = get_scenario(spec["id"])
    except (KeyError, ValueError) as exc:
        raise BundleError("Unknown synthetic scenario") from exc
    # Compare canonical JSON so bools cannot impersonate integer schema fields.
    if _canonical_bytes(spec) != _canonical_bytes(canonical):
        raise BundleError("Modified synthetic fixture; use the shipped scenario unchanged")
    return canonical


def _validate_observed_result(spec: dict[str, Any], agent: str, result: Any) -> None:
    from .core import run_scenario

    if not isinstance(result, dict) or result.get("agent") != agent:
        raise BundleError("Observed result must belong to the selected built-in agent")
    # Hashes establish integrity, not provenance. Comparing against the bounded,
    # deterministic built-in policy prevents a rehashed custom trace containing
    # customer data from being mislabeled as synthetic-only evidence.
    expected = run_scenario(spec, agent=agent)
    if _canonical_bytes(result) != _canonical_bytes(expected):
        raise BundleError("Observed result is not canonical synthetic demo evidence")


def create_bundle(spec: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Capture a built-in run, rejecting custom agents and customer trace data."""
    scenario = _canonical_scenario(spec)
    if not isinstance(result, dict):
        raise BundleError("Observed result must be an object")
    agent = result.get("agent")
    if not isinstance(agent, str) or agent not in _AGENTS:
        raise BundleError("Bundles support only the built-in unsafe and fixed demo agents")
    _validate_observed_result(scenario, agent, result)
    # Deep copies make the returned evidence independent of later caller edits.
    observed = json.loads(_canonical_bytes(result))
    bundle = {
        "schema_version": 1,
        "kind": _KIND,
        "synthetic_only": True,
        "scenario": scenario,
        "agent": agent,
        "observed_result": observed,
        "fingerprints": {
            "scenario_sha256": _digest(scenario),
            "result_sha256": _digest(observed),
            "simulator_sha256": simulator_fingerprint(),
        },
        "boundary": dict(_BOUNDARY),
    }
    if len(_canonical_bytes(bundle)) > MAX_BUNDLE_BYTES:
        raise BundleError("Bundle exceeds the 2 MiB size limit")
    return bundle


def write_bundle(path: str | Path, spec: dict[str, Any], result: dict[str, Any]) -> None:
    """Write a validated synthetic bundle to the caller's explicit destination."""
    bundle = create_bundle(spec, result)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(bundle, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if len(data.encode("utf-8")) > MAX_BUNDLE_BYTES:
        raise BundleError("Bundle exceeds the 2 MiB size limit")
    destination.write_text(data, encoding="utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise BundleError("Duplicate JSON fields are not allowed")
        obj[key] = value
    return obj


def _invalid_constant(value: str) -> None:
    raise BundleError(f"Non-finite JSON value is not allowed: {value}")


def read_bundle(path: str | Path) -> dict[str, Any]:
    """Validate all data, fingerprints, and simulator compatibility on import."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BUNDLE_BYTES + 1)
    except OSError as exc:
        raise BundleError(f"Cannot read bundle: {exc}") from exc
    if len(raw) > MAX_BUNDLE_BYTES:
        raise BundleError("Bundle exceeds the 2 MiB size limit")
    try:
        bundle = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise BundleError("Bundle must contain valid UTF-8 JSON") from exc
    if not isinstance(bundle, dict) or set(bundle) != _FIELDS:
        raise BundleError("Unknown or missing bundle fields")
    if type(bundle["schema_version"]) is not int or bundle["schema_version"] != 1:
        raise BundleError("Unsupported bundle schema version")
    if bundle["kind"] != _KIND or bundle["synthetic_only"] is not True:
        raise BundleError("Only synthetic support scenario bundles are supported")
    if _canonical_bytes(bundle["boundary"]) != _canonical_bytes(_BOUNDARY):
        raise BundleError("Unsupported bundle execution boundary")
    agent = bundle["agent"]
    if not isinstance(agent, str) or agent not in _AGENTS:
        raise BundleError("Unsupported built-in agent; imported commands are never executed")
    hashes = bundle["fingerprints"]
    if not isinstance(hashes, dict) or set(hashes) != _HASH_FIELDS:
        raise BundleError("Missing or unknown bundle fingerprints")
    for value in hashes.values():
        if not isinstance(value, str) or len(value) != 64 or any(
            char not in "0123456789abcdef" for char in value
        ):
            raise BundleError("Invalid SHA-256 fingerprint")
    if hashes["simulator_sha256"] != simulator_fingerprint():
        raise BundleError("Simulator source fingerprint differs; use the matching pack version")
    scenario = _canonical_scenario(bundle["scenario"])
    if hashes["scenario_sha256"] != _digest(scenario):
        raise BundleError("Scenario fingerprint does not match")
    if hashes["result_sha256"] != _digest(bundle["observed_result"]):
        raise BundleError("Observed result fingerprint does not match")
    _validate_observed_result(scenario, agent, bundle["observed_result"])
    return bundle


def reproduce_bundle(path: str | Path) -> dict[str, Any]:
    """Rerun the known local policy and compare exact deterministic evidence."""
    from .core import run_scenario

    bundle = read_bundle(path)
    result = run_scenario(bundle["scenario"], agent=bundle["agent"])
    expected = bundle["fingerprints"]["result_sha256"]
    actual = _digest(result)
    return {
        "matched": actual == expected,
        "scenario_id": bundle["scenario"]["id"],
        "agent": bundle["agent"],
        "expected_result_sha256": expected,
        "actual_result_sha256": actual,
        "result": result,
    }
