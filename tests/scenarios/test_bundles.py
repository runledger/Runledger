from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from runledger.scenarios import bundles
from runledger.scenarios.core import run_scenario
from runledger.scenarios.pack import get_scenario, scenarios


def _save(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@pytest.fixture
def incident() -> dict:
    spec = get_scenario("timeout-after-commit")
    return bundles.create_bundle(spec, run_scenario(spec, agent="unsafe"))


@pytest.mark.parametrize("agent", ["unsafe", "fixed"])
def test_every_shipped_scenario_round_trips_and_reproduces(tmp_path: Path, agent: str) -> None:
    for spec in scenarios():
        result = run_scenario(spec, agent=agent)
        path = tmp_path / f"{spec['id']}-{agent}.json"
        bundles.write_bundle(path, spec, result)
        imported = bundles.read_bundle(path)
        replayed = bundles.reproduce_bundle(path)
        assert imported["synthetic_only"] is True
        assert imported["boundary"]["automatic_redaction"] is False
        assert imported["boundary"]["external_network"] is False
        assert replayed["matched"] is True
        assert replayed["result"] == result
        assert replayed["actual_result_sha256"] == replayed["expected_result_sha256"]


def test_failed_outcome_is_successfully_reproduced(tmp_path: Path, incident: dict) -> None:
    replayed = bundles.reproduce_bundle(_save(tmp_path / "incident.json", incident))
    assert replayed["matched"] is True
    assert replayed["result"]["passed"] is False
    assert len(replayed["result"]["effects"]) == 2


def test_export_is_detached_from_callers_mutable_result() -> None:
    spec = get_scenario("timeout-after-commit")
    result = run_scenario(spec, agent="unsafe")
    exported = bundles.create_bundle(spec, result)
    result["trace"].clear()
    spec["title"] = "changed"
    assert exported["observed_result"]["trace"]
    assert exported["scenario"]["title"] != "changed"


def test_modified_fixture_is_rejected_even_with_recomputed_hash(tmp_path: Path, incident: dict) -> None:
    incident["scenario"]["initial_state"]["order"]["customer_id"] = "real@example.com"
    incident["fingerprints"]["scenario_sha256"] = _hash(incident["scenario"])
    with pytest.raises(bundles.BundleError, match="Modified synthetic fixture"):
        bundles.read_bundle(_save(tmp_path / "modified.json", incident))


def test_tampered_result_hash_is_rejected(tmp_path: Path, incident: dict) -> None:
    incident["observed_result"]["passed"] = True
    with pytest.raises(bundles.BundleError, match="result fingerprint"):
        bundles.read_bundle(_save(tmp_path / "modified.json", incident))


def test_rehashed_custom_trace_cannot_be_labeled_synthetic(tmp_path: Path, incident: dict) -> None:
    incident["observed_result"]["trace"].append({"type": "log", "message": "real@example.com"})
    incident["fingerprints"]["result_sha256"] = _hash(incident["observed_result"])
    with pytest.raises(bundles.BundleError, match="not canonical synthetic"):
        bundles.read_bundle(_save(tmp_path / "modified.json", incident))


def test_export_refuses_custom_agent_data() -> None:
    spec = get_scenario("happy-path")
    result = run_scenario(spec, agent="fixed")
    result["agent"] = "custom"
    with pytest.raises(bundles.BundleError, match="built-in unsafe and fixed"):
        bundles.create_bundle(spec, result)


@pytest.mark.parametrize("version", [2, True, "1", None])
def test_unknown_versions_fail_closed(tmp_path: Path, incident: dict, version: object) -> None:
    incident["schema_version"] = version
    with pytest.raises(bundles.BundleError, match="schema version"):
        bundles.read_bundle(_save(tmp_path / "modified.json", incident))


def test_commands_in_imported_data_are_never_executed(tmp_path: Path, incident: dict) -> None:
    sentinel = tmp_path / "should-not-exist.txt"
    incident["agent"] = ["python", "-c", f"open({str(sentinel)!r}, 'w').write('unsafe')"]
    with pytest.raises(bundles.BundleError, match="commands are never executed"):
        bundles.read_bundle(_save(tmp_path / "command.json", incident))
    assert not sentinel.exists()
    incident["agent"] = "unsafe"
    incident["command"] = ["touch", str(sentinel)]
    with pytest.raises(bundles.BundleError, match="Unknown or missing bundle fields"):
        bundles.read_bundle(_save(tmp_path / "command.json", incident))
    assert not sentinel.exists()


def test_changed_simulator_sources_are_rejected(tmp_path: Path, incident: dict, monkeypatch) -> None:
    path = _save(tmp_path / "incident.json", incident)
    monkeypatch.setattr(bundles, "simulator_fingerprint", lambda: "f" * 64)
    with pytest.raises(bundles.BundleError, match="source fingerprint differs"):
        bundles.read_bundle(path)


def test_simulator_fingerprint_is_portable_across_checkout_line_endings(monkeypatch) -> None:
    original = bundles.simulator_fingerprint()
    read_bytes = Path.read_bytes

    def windows_line_endings(path):
        data = read_bytes(path)
        if path.name in {"core.py", "agents.py", "pack.py"}:
            return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return data

    monkeypatch.setattr(Path, "read_bytes", windows_line_endings)
    assert bundles.simulator_fingerprint() == original


@pytest.mark.parametrize("fingerprint", ["short", "g" * 64, 42])
def test_invalid_fingerprints_are_rejected(tmp_path: Path, incident: dict, fingerprint: object) -> None:
    incident["fingerprints"]["result_sha256"] = fingerprint
    with pytest.raises(bundles.BundleError, match="Invalid SHA-256"):
        bundles.read_bundle(_save(tmp_path / "bad-hash.json", incident))


def test_oversized_file_is_bounded_before_decoding(tmp_path: Path) -> None:
    path = tmp_path / "huge.json"
    path.write_bytes(b" " * (bundles.MAX_BUNDLE_BYTES + 1))
    with pytest.raises(bundles.BundleError, match="2 MiB"):
        bundles.read_bundle(path)


@pytest.mark.parametrize("payload", ['{"schema_version":1,"schema_version":2}', '{"x":NaN}', "[]"])
def test_ambiguous_or_nonobject_json_is_rejected(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(bundles.BundleError):
        bundles.read_bundle(path)
