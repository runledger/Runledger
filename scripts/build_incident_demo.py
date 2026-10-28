"""Generate public evidence using a fictional production-format export only."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from runledger.incidents.importer import import_incident
from runledger.incidents.replay import evaluate_incident, replay_incident


def main() -> None:
    source = ROOT / "examples/incidents/production-example.json"
    adapter = ROOT / "examples/incidents/replay_agent.py"
    bundle = import_incident(source)
    evaluation = evaluate_incident(bundle["incident"])
    replay = replay_incident(bundle["incident"], [sys.executable, str(adapter)])
    if not replay["matched"] or evaluation["passed"] or len(evaluation["effects"]) != 2:
        raise RuntimeError("Incident showcase must reproduce the captured double-refund failure")
    demo = {"schema_version": 1, "example_label": "Fictional production-format incident",
            "redaction": bundle["redaction"], "incident": bundle["incident"],
            "evaluation": evaluation, "replay": replay,
            "downloads": {"source": "/templates/support-agent/runledger-scenario-source.zip",
                          "example": "/templates/incidents/production-example.json",
                          "bundle": "/templates/incidents/redacted-incident.json",
                          "guide": "/templates/incidents/README.md"}}
    folder = ROOT / "templates/incidents"
    folder.mkdir(parents=True, exist_ok=True)
    outputs = {"demo.json": demo, "redacted-incident.json": bundle}
    for filename, payload in outputs.items():
        (folder / filename).write_bytes((json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("utf-8"))
    (folder / "production-example.json").write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
    (folder / "README.md").write_bytes((ROOT / "docs/production-incidents.md").read_bytes().replace(b"\r\n", b"\n"))
    source_paths = sorted((ROOT / "src/runledger/incidents").glob("*.py")) + [source, adapter, ROOT / "docs/production-incidents.md"]
    manifest = {"schema_version": 1, "source_text_normalization": "lf",
                "sources": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for path in source_paths},
                "files": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in [*outputs, "production-example.json", "README.md"]}}
    (folder / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    print("Built fictional production-incident showcase: redacted import, ordered replay MATCHED, business rules FAIL.")


if __name__ == "__main__":
    main()
