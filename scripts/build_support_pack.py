"""Build public evidence and a dependency-free demo from the real scenario engine.

Run after simulator changes. The site build checks these fingerprints so stale
or hand-edited screenshots/data cannot silently replace executable evidence.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from runledger.scenarios.bundles import create_bundle, simulator_fingerprint
from runledger.scenarios.cli import verify_scenarios
from runledger.scenarios.pack import scenarios

DESTINATION = ROOT / "templates" / "support-agent"
SOURCE_FILES = ["__init__.py", "core.py", "agents.py", "pack.py", "bundles.py", "reports.py", "cli.py"]
FULL_SOURCE_FILES = ["pyproject.toml", "README.md", "LICENSE", "MANIFEST.in", "CHANGELOG.md", "docs/support-agent-pack.md",
                     "docs/production-incidents.md", "examples/support-agent/agent.py",
                     "examples/support-agent/verify_adapter.py", "examples/incidents/production-example.json",
                     "examples/incidents/replay_agent.py", "examples/incidents/replay_example.py"]
FULL_SOURCE_FILES += [
    "examples/incident-to-fix/README.md",
    "examples/incident-to-fix/verify.py",
    "examples/openchatbi-handoff/README.md",
    "examples/openchatbi-handoff/capture.py",
    "examples/openchatbi-handoff/adapter_bridge.py",
    "examples/openchatbi-handoff/manifest.json",
    "docs/customer-handoff.md",
    "docs/adoption-evidence.md",
    "docs/integrations.md",
    "docs/developer-trial.md",
    "docs/setup-verification.md",
    "templates/customer-handoff/README.md",
    "templates/customer-handoff/intake.md",
    "templates/customer-handoff/scope.md",
    "templates/customer-handoff/evidence.md",
    "templates/customer-handoff/acceptance.md",
]
LAUNCHER = b'from runledger.scenarios.cli import main\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def source_text(path: Path) -> bytes:
    """Canonical text preserves source hashes across Windows and Unix checkouts."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for filename, data in sorted(entries.items()):
            entry = zipfile.ZipInfo(filename, (2026, 10, 27, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            package.writestr(entry, data)
    return archive.getvalue()


def full_source_entries() -> dict[str, bytes]:
    # Explicit package tree and named supporting files only. Never archive the
    # workspace wholesale: it also contains private environment and runtime data.
    package_root = ROOT / "src" / "runledger"
    paths = [path for path in package_root.rglob("*.py") if "__pycache__" not in path.parts]
    paths.extend(ROOT / name for name in FULL_SOURCE_FILES)
    entries = {}
    for path in sorted(paths):
        if path.is_symlink() or ROOT not in path.resolve().parents:
            raise RuntimeError("Refusing linked or external source: " + str(path))
        entries[path.relative_to(ROOT).as_posix()] = source_text(path)
    return entries


def build() -> None:
    specs = scenarios()
    comparisons = verify_scenarios(specs)
    if not all(item["comparison"]["verified"] for item in comparisons):
        raise RuntimeError("Fixed policy must pass all five scenarios before publishing")
    timeout = next(item for item in comparisons if item["id"] == "timeout-after-commit")
    if timeout["comparison"]["before_refunds"] != 2 or timeout["comparison"]["after_refunds"] != 1:
        raise RuntimeError("Refund showcase no longer demonstrates the tested failure and fix")
    fixture = {"schema_version": 1, "pack_version": "support-agent-v1", "synthetic_only": True,
               "simulator_sha256": simulator_fingerprint(), "scenarios": comparisons,
               "reproduction": {"download_url": "/templates/support-agent/runledger-support-agent.zip",
                                "source_download_url": "/templates/support-agent/runledger-scenario-source.zip",
                                "command": "python run_demo.py verify --out results"}}
    incident = create_bundle(next(spec for spec in specs if spec["id"] == timeout["id"]), timeout["before"])
    entries = {"run_demo.py": LAUNCHER,
               "runledger/__init__.py": b'"""RunLedger portable synthetic support-agent pack."""\n',
               "README.md": source_text(ROOT / "docs" / "support-agent-pack.md"),
               "LICENSE": source_text(ROOT / "LICENSE"),
               "scenarios.json": canonical(specs),
               "incident.json": canonical(incident),
               "regression.yml": source_text(ROOT / "templates" / "support-agent" / "regression.yml")}
    sources = {}
    for filename in SOURCE_FILES:
        source = ROOT / "src" / "runledger" / "scenarios" / filename
        data = source_text(source)
        entries["runledger/scenarios/" + filename] = data
        sources[source.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
    for relative in ("docs/support-agent-pack.md", "templates/support-agent/regression.yml"):
        sources[relative] = hashlib.sha256(source_text(ROOT / relative)).hexdigest()
    archive = zip_bytes(entries)
    source_entries = full_source_entries()
    sources.update({name: hashlib.sha256(data).hexdigest() for name, data in source_entries.items()})
    source_archive = zip_bytes(source_entries)
    outputs = {"demo-results.json": canonical(fixture), "incident.json": canonical(incident),
               "runledger-support-agent.zip": archive,
               "runledger-scenario-source.zip": source_archive,
               "README.md": entries["README.md"]}
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for filename, data in outputs.items():
        (DESTINATION / filename).write_bytes(data)
    manifest = {"schema_version": 1, "pack_version": "support-agent-v1",
                "source_text_normalization": "lf",
                "simulator_sha256": simulator_fingerprint(), "sources": sources,
                "files": {filename: hashlib.sha256(data).hexdigest() for filename, data in outputs.items()}}
    (DESTINATION / "manifest.json").write_bytes(canonical(manifest))
    print(f"Built support-agent-v1: {len(specs)} verified scenarios, {len(archive):,}-byte portable ZIP, "
          f"{len(source_archive):,}-byte full source ZIP")


if __name__ == "__main__":
    build()
