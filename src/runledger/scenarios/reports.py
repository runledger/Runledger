"""Deterministic comparison and local artifacts for the support-agent pack."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path


def compare_runs(before: dict, after: dict) -> dict:
    if before["scenario_id"] != after["scenario_id"]:
        raise ValueError("Comparison requires the same scenario")
    if before["initial_state"] != after["initial_state"]:
        raise ValueError("Comparison requires the same initial state")
    # Compare actions, not bookkeeping or machine-dependent timing.
    left = [event for event in before["trace"] if event["type"] == "tool_call"]
    right = [event for event in after["trace"] if event["type"] == "tool_call"]
    divergence = None

    def difference(a: dict | None, b: dict | None, action_index: int) -> dict:
        before_step = a.get("step") if a else None
        after_step = b.get("step") if b else None
        return {"step": before_step if before_step is not None else after_step,
                "action_index": action_index, "before_step": before_step,
                "after_step": after_step, "before": a, "after": b}

    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else None
        b = right[index] if index < len(right) else None
        action_a = {key: value for key, value in a.items() if key not in {"step", "call_id"}} if a else None
        action_b = {key: value for key, value in b.items() if key not in {"step", "call_id"}} if b else None
        if action_a != action_b:
            divergence = difference(a, b, index + 1)
            break
    if divergence is None and before["output"] != after["output"]:
        final_before = next((event for event in before["trace"]
                             if event["type"] == "final_output"), None)
        final_after = next((event for event in after["trace"]
                            if event["type"] == "final_output"), None)
        divergence = difference(final_before, final_after, len(left) + 1)
    return {
        "first_divergence": divergence,
        "verified": bool(after["passed"]),
        "repaired": not before["passed"] and after["passed"],
        "before_refunds": len([e for e in before["effects"] if e["type"] == "refund"]),
        "after_refunds": len([e for e in after["effects"] if e["type"] == "refund"]),
        "before_amount_cents": sum(e["amount_cents"] for e in before["effects"] if e["type"] == "refund"),
        "after_amount_cents": sum(e["amount_cents"] for e in after["effects"] if e["type"] == "refund"),
    }


def _json(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json(value) + "\n", encoding="utf-8")


def _run_html(run: dict) -> str:
    status = "PASS" if run["passed"] else "FAIL"
    refund_count = sum(effect["type"] == "refund" for effect in run["effects"])
    rules = "".join(
        '<li><strong class="' + ("pass" if rule["passed"] else "fail") + '">'
        + ("PASS" if rule["passed"] else "FAIL") + "</strong> "
        + escape(str(rule["label"])) + "<small>"
        + escape(str(rule.get("detail", ""))) + "</small></li>"
        for rule in run["assertions"]
    )
    events = "".join(
        "<details><summary>" + escape(str(event.get("step", ""))) + " · "
        + escape(str(event["type"])) + " " + escape(str(event.get("name", "")))
        + "</summary><pre>" + escape(_json(event)) + "</pre></details>"
        for event in run["trace"]
    )
    return (
        '<section class="run"><h3>' + escape(str(run["agent"])) + " · " + status
        + '</h3><p>Committed refunds: <strong>' + str(refund_count)
        + "</strong></p><ul>" + rules + "</ul><h4>Final output</h4><pre>"
        + escape(_json(run["output"])) + "</pre>"
        + ("<p class=fail>" + escape(str(run["error"])) + "</p>" if run.get("error") else "")
        + "<h4>Committed business effects</h4><pre>" + escape(_json(run["effects"]))
        + "</pre><h4>Event trace</h4>" + events + "</section>"
    )


def write_report(path: Path, *, runs: list[dict] | None = None, comparisons: list[dict] | None = None) -> None:
    sections = []
    for item in comparisons or []:
        comparison = item["comparison"]
        divergence = comparison["first_divergence"]
        sections.append(
            "<article><h2>" + escape(item["title"]) + "</h2><p>"
            + escape(item["description"]) + "</p><p>Candidate: <strong class=\""
            + ("pass" if comparison["verified"] else "fail") + "\">"
            + ("PASS" if comparison["verified"] else "FAIL") + "</strong> · "
            + str(comparison["before_refunds"]) + " → " + str(comparison["after_refunds"])
            + " committed refunds</p><details><summary>First behavioral divergence</summary><pre>"
            + escape(_json(divergence)) + "</pre></details><div class=columns>"
            + _run_html(item["before"]) + _run_html(item["after"]) + "</div></article>"
        )
    for run in runs or []:
        sections.append("<article><h2>" + escape(run["title"]) + "</h2>" + _run_html(run) + "</article>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>RunLedger · Support-agent evidence</title>
<style>body{font:16px/1.6 system-ui,sans-serif;background:#0b101c;color:#e3e9f5;margin:0;padding:32px}main{max-width:1200px;margin:auto}h1{font-size:clamp(28px,4vw,44px)}h2,h3{line-height:1.3}article{padding:24px 0;border-top:1px solid #38445a}.columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.run{background:#151e2e;padding:24px;border-radius:16px;min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 ui-monospace,monospace;background:#0b101c;padding:16px;border-radius:8px}small{display:block;color:#bbc8dc}.pass{color:#6ee7b7}.fail{color:#fda4af}li{margin:12px 0}ul{padding-left:20px}summary{cursor:pointer;padding:8px 0}footer{color:#bbc8dc;margin-top:30px}@media(max-width:750px){body{padding:20px}.columns{grid-template-columns:1fr}.run{padding:16px}}</style></head><body><main>
<p>RUNLEDGER / SUPPORT-AGENT SCENARIO PACK v1</p><h1>What actually happened?</h1>
<p>Local simulated payments, explicit business rules, and reproducible evidence. Built-in demo policies are deterministic; no live model or payment API is called. A custom agent is a locally executed program, not a sandbox.</p>
""" + "".join(sections) + "<footer>Results cover these fixtures and action policies. They do not certify production safety or evaluate model judgment.</footer></main></body></html>", encoding="utf-8")


def write_run_artifacts(directory: Path, run: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "result.json", run)
    (directory / "trace.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in run["trace"]), encoding="utf-8")
    write_report(directory / "report.html", runs=[run])
    write_junit(directory / "junit.xml", [run])


def write_junit(path: Path, runs: list[dict]) -> None:
    suite = ET.Element("testsuite", name="runledger-support-agent", tests=str(len(runs)),
                       failures=str(sum(not run["passed"] for run in runs)))
    for run in runs:
        case = ET.SubElement(suite, "testcase", name=run["scenario_id"], classname="support-agent." + run["agent"])
        if not run["passed"]:
            failure = ET.SubElement(case, "failure", message="Business-effect invariant failed")
            failure.text = _json({"assertions": [r for r in run["assertions"] if not r["passed"]], "error": run["error"]})
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
