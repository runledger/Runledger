"""Escaped, local reports for redacted incident evidence and ordered replay."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET

from .importer import write_json


def _pretty(value: object) -> str:
    return escape(json.dumps(value, indent=2, ensure_ascii=True))


def write_artifacts(directory: Path, bundle: dict, evaluation: dict,
                    replay: dict | None = None) -> None:
    write_json(directory / "incident.json", bundle)
    write_json(directory / "redaction-report.json", bundle["redaction"])
    write_json(directory / "evaluation.json", evaluation)
    if replay is not None:
        write_json(directory / "replay.json", replay)
    (directory / "trace.jsonl").write_text("".join(json.dumps(event, ensure_ascii=True) + "\n"
                                                   for event in bundle["incident"]["events"]), encoding="utf-8")
    gate_passed = evaluation["passed"] and (replay is None or replay["matched"])
    suite = ET.Element("testsuite", name="runledger-production-incident", tests="1",
                       failures="0" if gate_passed else "1")
    case = ET.SubElement(suite, "testcase", name="incident-business-rules")
    if not gate_passed:
        failure = ET.SubElement(case, "failure", message="Incident rules failed or replay diverged")
        failure.text = json.dumps({"assertions": evaluation["assertions"],
                                   "matched": replay["matched"] if replay else None}, ensure_ascii=True)
    ET.ElementTree(suite).write(directory / "junit.xml", encoding="utf-8", xml_declaration=True)
    status = "PASS" if evaluation["passed"] else "FAIL / INCONCLUSIVE"
    replay_status = ("MATCHED" if replay["matched"] else "DIVERGED / AGENT ERROR") if replay else "NOT RUN"
    rules = "".join("<tr><td>" + escape(str(item["id"])) + "</td><td>"
                    + ("PASS" if item["passed"] else "FAIL / INCONCLUSIVE") + "</td><td>"
                    + escape(str(item.get("detail", ""))) + "</td></tr>" for item in evaluation["assertions"])
    events = "".join("<details><summary>" + str(index) + " · " + escape(event["type"])
                     + " " + escape(str(event.get("name", ""))) + "</summary><pre>"
                     + _pretty(event) + "</pre></details>" for index, event in enumerate(bundle["incident"]["events"], 1))
    html = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RunLedger · Imported incident</title>
<style>body{font:16px/1.65 system-ui,sans-serif;background:#0b101c;color:#dce7fa;margin:0;padding:32px}main{max-width:1050px;margin:auto}h1{font-size:38px;line-height:1.2}h2{margin-top:36px}pre{background:#121f34;padding:20px;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.7 monospace;border-radius:8px}table{width:100%;border-collapse:collapse}td,th{padding:14px;text-align:left;border-bottom:1px solid #344058;overflow-wrap:anywhere}.notice{border:1px solid #987342;background:#30271d;padding:20px}.cards{display:flex;flex-wrap:wrap;gap:20px}.cards p{flex:1;background:#152237;padding:20px;min-width:220px}summary{padding:10px;cursor:pointer}small{color:#9fb3cf}@media(max-width:600px){body{padding:20px}h1{font-size:28px}table{font-size:13px}td,th{padding:8px}}</style></head><body><main>
<p>RUNLEDGER / PRODUCTION INCIDENT IMPORT</p><h1>Reproduce the trace. Check the effects.</h1>
<div class="notice"><strong>Review required before sharing.</strong> Known secrets, identifiers, and freeform fields are transformed during import. Redaction cannot identify every private value, and transformations can change agent behavior. This report contains local evidence; it is not a certification of anonymity or production safety.</div>
"""
    html += '<div class="cards"><p>Agent replay<br><strong>' + replay_status + '</strong></p><p>Business rules<br><strong>' + status + "</strong></p></div>"
    html += "<p>A matched replay may reproduce a failing incident. A passing CI gate requires both a matching replay and passing business rules. Imported effects are historical observations from the exporter, not newly executed provider actions.</p>"
    html += "<h2>Redaction review</h2><pre>" + _pretty(bundle["redaction"]) + "</pre>"
    html += "<h2>Business rules</h2><table><tr><th>Rule</th><th>Result</th><th>Evidence</th></tr>" + rules + "</table>"
    if replay is not None:
        html += "<h2>Replay result</h2><pre>" + _pretty({key: value for key, value in replay.items() if key not in {"trace", "expected", "observed"}}) + "</pre>"
    html += "<h2>Sanitized input</h2><pre>" + _pretty(bundle["incident"]["input"]) + "</pre>"
    html += "<h2>Recorded events in order</h2>" + events
    html += "<h2>Execution boundary</h2><pre>" + _pretty(bundle["boundary"]) + "</pre>"
    html += "<p><small>Bundle integrity (not a signature): " + escape(bundle["integrity"]["sha256"]) + "</small></p></main></body></html>"
    (directory / "report.html").write_text(html, encoding="utf-8")
