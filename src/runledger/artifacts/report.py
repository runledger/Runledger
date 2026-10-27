from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Template
from jinja2.utils import htmlsafe_json_dumps

from runledger.util.redaction import redact

_REPORT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RunLedger Report</title>
  <style>
    :root {
      --bg: #f5efe6;
      --bg2: #e6f0f5;
      --ink: #1f2a30;
      --muted: #5b6b75;
      --accent: #1f7a8c;
      --accent-2: #e07a5f;
      --card: #fffaf3;
      --border: rgba(31, 42, 48, 0.12);
      --shadow: 0 12px 30px rgba(31, 42, 48, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Space Grotesk", "Avenir Next", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1200px 500px at 10% -10%, #f8d9c0, transparent 60%),
        radial-gradient(900px 400px at 100% 0%, #cfe6f3, transparent 55%),
        linear-gradient(120deg, var(--bg), var(--bg2));
      min-height: 100vh;
    }
    header {
      padding: 32px 24px 12px;
      max-width: 1200px;
      margin: 0 auto;
      animation: rise 0.7s ease forwards;
    }
    h1 {
      margin: 0;
      font-size: clamp(28px, 4vw, 42px);
      letter-spacing: -0.02em;
    }
    .subtitle {
      color: var(--muted);
      margin-top: 6px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 6px 12px;
      font-size: 12px;
      background: rgba(31, 42, 48, 0.08);
      color: var(--ink);
      margin-right: 8px;
    }
    main {
      max-width: 1200px;
      margin: 0 auto;
      padding: 0 24px 40px;
      display: grid;
      gap: 24px;
    }
    .grid {
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
      box-shadow: var(--shadow);
      animation: rise 0.7s ease forwards;
    }
    .card h3 {
      margin: 0 0 6px;
      font-size: 16px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .card .value {
      font-size: 26px;
      font-weight: 600;
    }
    .section-title {
      margin: 8px 0;
      font-size: 20px;
    }
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }
    button.filter {
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.9);
      border-radius: 999px;
      padding: 6px 12px;
      cursor: pointer;
      font-weight: 600;
    }
    button.filter.active {
      background: var(--accent);
      color: #fff;
      border-color: transparent;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
    }
    tr:hover {
      background: rgba(31, 122, 140, 0.08);
      cursor: pointer;
    }
    .status {
      font-weight: 700;
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: 0.08em;
    }
    .status.pass { color: #1b7f5a; }
    .status.fail { color: #c0392b; }
    .status.error { color: #c06a00; }
    .status.skipped { color: #7b7b7b; }
    .detail {
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }
    .trace {
      max-height: 340px;
      overflow: auto;
      background: #0f1c1f;
      color: #f4f1ed;
      padding: 12px;
      border-radius: 12px;
      font-family: "IBM Plex Mono", "Consolas", monospace;
      font-size: 12px;
    }
    .trace-event {
      border-left: 3px solid var(--accent-2);
      padding: 8px 10px;
      margin-bottom: 8px;
      background: rgba(224, 122, 95, 0.08);
    }
    .trace-event strong {
      display: block;
      color: #ffd166;
    }
    .badge {
      display: inline-block;
      background: rgba(31, 122, 140, 0.15);
      color: var(--accent);
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 12px;
      margin-right: 6px;
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @media (max-width: 720px) {
      header { padding: 24px 16px 8px; }
      main { padding: 0 16px 32px; }
      table { font-size: 13px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>RunLedger Report</h1>
    <div class="subtitle" id="suite-subtitle"></div>
    <div id="meta"></div>
  </header>
  <main>
    <section class="grid" id="kpis"></section>
    <section class="card">
      <h2 class="section-title">Cases</h2>
      <div class="filters" id="filters"></div>
      <table>
        <thead>
          <tr>
            <th>Case</th>
            <th>Status</th>
            <th>Wall (ms)</th>
            <th>Tool Calls</th>
            <th>Tool Errors</th>
          </tr>
        </thead>
        <tbody id="case-rows"></tbody>
      </table>
    </section>
    <section class="card">
      <h2 class="section-title">Case Detail</h2>
      <div class="detail">
        <div>
          <div id="case-meta"></div>
          <div id="case-metrics"></div>
          <div id="case-failure"></div>
        </div>
        <div>
          <div class="filters" id="trace-filters"></div>
          <div class="trace" id="trace-view"></div>
        </div>
      </div>
    </section>
  </main>
  <script id="runledger-data" type="application/json">{{ data_json }}</script>
  <script>
    const data = JSON.parse(document.getElementById("runledger-data").textContent);
    const summary = data.summary || {};
    const cases = summary.cases || [];
    const traces = data.traces || {};

    // Agent and tool output is untrusted, even in an offline report.
    function textElement(tag, text, className) {
      const node = document.createElement(tag);
      node.textContent = String(text);
      if (className) node.className = className;
      return node;
    }

    function metricLine(...parts) {
      const line = document.createElement("p");
      line.append(...parts);
      return line;
    }

    const suiteName = summary.suite?.name || "unknown";
    const runId = summary.run?.run_id || "n/a";
    const mode = summary.run?.mode || summary.suite?.tool_mode || "n/a";
    const status = summary.run?.exit_status || "n/a";

    document.getElementById("suite-subtitle").textContent =
      `${suiteName} • run ${runId}`;

    const meta = document.getElementById("meta");
    meta.replaceChildren(
      textElement("span", `Mode: ${mode}`, "pill"),
      textElement("span", `Status: ${status}`, "pill"),
      textElement("span", `Generated: ${summary.generated_at || "n/a"}`, "pill")
    );

    const aggregates = summary.aggregates || {};
    const metrics = aggregates.metrics || {};
    const passRate = aggregates.pass_rate !== undefined ? (aggregates.pass_rate * 100).toFixed(1) + "%" : "n/a";

    const kpis = [
      { label: "Pass Rate", value: passRate },
      { label: "Cases Pass", value: aggregates.cases_pass ?? "n/a" },
      { label: "Cases Fail", value: aggregates.cases_fail ?? "n/a" },
      { label: "Cases Error", value: aggregates.cases_error ?? "n/a" },
      { label: "p95 Wall (ms)", value: metrics.wall_ms?.p95 ?? "n/a" },
      { label: "Avg Wall (ms)", value: metrics.wall_ms?.mean ?? "n/a" },
      { label: "p95 Tool Calls", value: metrics.tool_calls?.p95 ?? "n/a" },
      { label: "Avg Tool Calls", value: metrics.tool_calls?.mean ?? "n/a" },
    ];

    const kpiWrap = document.getElementById("kpis");
    kpis.forEach((item, idx) => {
      const card = document.createElement("div");
      card.className = "card";
      card.style.animationDelay = `${0.05 * idx}s`;
      card.append(
        textElement("h3", item.label),
        textElement("div", item.value, "value")
      );
      kpiWrap.appendChild(card);
    });

    const statusFilters = ["all", "pass", "fail", "error", "skipped"];
    const filters = document.getElementById("filters");
    let activeFilter = "all";

    function renderFilters() {
      filters.replaceChildren();
      statusFilters.forEach((filter) => {
        const btn = document.createElement("button");
        btn.className = "filter" + (filter === activeFilter ? " active" : "");
        btn.textContent = filter.toUpperCase();
        btn.onclick = () => {
          activeFilter = filter;
          renderFilters();
          renderTable();
        };
        filters.appendChild(btn);
      });
    }

    function renderTable() {
      const tbody = document.getElementById("case-rows");
      tbody.replaceChildren();
      const filtered = cases.filter((item) => {
        if (activeFilter === "all") return true;
        return item.status === activeFilter;
      });
      filtered.forEach((item) => {
        const row = document.createElement("tr");
        const statusCell = document.createElement("td");
        const statusClass = statusFilters.includes(item.status) ? item.status : "";
        statusCell.appendChild(textElement("span", item.status, `status ${statusClass}`));
        row.append(
          textElement("td", item.id),
          statusCell,
          textElement("td", item.wall_ms),
          textElement("td", item.tool_calls),
          textElement("td", item.tool_errors)
        );
        row.onclick = () => selectCase(item.id);
        tbody.appendChild(row);
      });
      if (filtered.length && !selectedCaseId) {
        selectCase(filtered[0].id);
      }
    }

    const traceFilters = ["all", "task_start", "tool_call", "tool_result", "final_output", "log", "case_end"];
    let activeTraceFilter = "all";

    function renderTraceFilters() {
      const container = document.getElementById("trace-filters");
      container.replaceChildren();
      traceFilters.forEach((filter) => {
        const btn = document.createElement("button");
        btn.className = "filter" + (filter === activeTraceFilter ? " active" : "");
        btn.textContent = filter.replace("_", " ").toUpperCase();
        btn.onclick = () => {
          activeTraceFilter = filter;
          renderTrace();
          renderTraceFilters();
        };
        container.appendChild(btn);
      });
    }

    let selectedCaseId = null;

    function selectCase(caseId) {
      selectedCaseId = caseId;
      const item = cases.find((c) => c.id === caseId);
      if (!item) return;
      document.getElementById("case-meta").replaceChildren(
        textElement("span", `Case: ${item.id}`, "badge"),
        textElement("span", `Status: ${item.status}`, "badge"),
        textElement("span", `Assertions: ${item.assertions?.failed ?? 0}/${item.assertions?.total ?? 0}`, "badge")
      );
      document.getElementById("case-metrics").replaceChildren(
        metricLine("Wall: ", textElement("strong", item.wall_ms), " ms"),
        metricLine("Tool calls: ", textElement("strong", item.tool_calls),
          " • errors: ", textElement("strong", item.tool_errors)),
        metricLine("Tokens in/out: ", textElement("strong", item.tokens_in ?? "n/a"),
          " / ", textElement("strong", item.tokens_out ?? "n/a")),
        metricLine("Cost USD: ", textElement("strong", item.cost_usd ?? "n/a"),
          " • Steps: ", textElement("strong", item.steps ?? "n/a"))
      );
      const failure = item.failure_reason || "None";
      document.getElementById("case-failure").replaceChildren(
        metricLine("Failure: ", textElement("strong", failure))
      );
      renderTrace();
    }

    function renderTrace() {
      const traceView = document.getElementById("trace-view");
      const events = traces[selectedCaseId] || [];
      const filtered = events.filter((event) => {
        if (activeTraceFilter === "all") return true;
        return event.type === activeTraceFilter;
      });
      traceView.replaceChildren();
      if (!filtered.length) {
        traceView.appendChild(textElement("em", "No trace events to display."));
        return;
      }
      filtered.forEach((event) => {
        const entry = document.createElement("div");
        entry.className = "trace-event";
        entry.append(
          textElement("strong", event.type),
          textElement("pre", JSON.stringify(event, null, 2))
        );
        traceView.appendChild(entry);
      });
    }

    renderFilters();
    renderTraceFilters();
    renderTable();
  </script>
</body>
</html>
"""


def _load_run_log(run_path: Path) -> dict[str, list[dict[str, Any]]]:
    traces: dict[str, list[dict[str, Any]]] = {}
    if not run_path.is_file():
        return traces
    for line in run_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        case_id = str(event.get("case_id", "unknown"))
        traces.setdefault(case_id, []).append(event)
    return traces


def write_report(
    run_dir: Path,
    *,
    summary: dict[str, Any],
    run_log_path: Path | None = None,
) -> Path:
    if run_log_path is None:
        run_log_path = run_dir / "run.jsonl"
    traces = _load_run_log(run_log_path)
    report_data = {
        "summary": redact(summary),
        "traces": redact(traces),
    }
    data_json = htmlsafe_json_dumps(report_data, ensure_ascii=False)
    html = Template(_REPORT_TEMPLATE).render(data_json=data_json)
    report_path = run_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path
