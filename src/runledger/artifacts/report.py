from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Template
from markupsafe import Markup

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

    const suiteName = summary.suite?.name || "unknown";
    const runId = summary.run?.run_id || "n/a";
    const mode = summary.run?.mode || summary.suite?.tool_mode || "n/a";
    const status = summary.run?.exit_status || "n/a";

    document.getElementById("suite-subtitle").textContent =
      `${suiteName} • run ${runId}`;

    const meta = document.getElementById("meta");
    meta.innerHTML = [
      `<span class="pill">Mode: ${mode}</span>`,
      `<span class="pill">Status: ${status}</span>`,
      `<span class="pill">Generated: ${summary.generated_at || "n/a"}</span>`
    ].join("");

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
      card.innerHTML = `<h3>${item.label}</h3><div class="value">${item.value}</div>`;
      kpiWrap.appendChild(card);
    });

    const statusFilters = ["all", "pass", "fail", "error", "skipped"];
    const filters = document.getElementById("filters");
    let activeFilter = "all";

    function renderFilters() {
      filters.innerHTML = "";
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
      tbody.innerHTML = "";
      const filtered = cases.filter((item) => {
        if (activeFilter === "all") return true;
        return item.status === activeFilter;
      });
      filtered.forEach((item) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${item.id}</td>
          <td><span class="status ${item.status}">${item.status}</span></td>
          <td>${item.wall_ms}</td>
          <td>${item.tool_calls}</td>
          <td>${item.tool_errors}</td>
        `;
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
      container.innerHTML = "";
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
      document.getElementById("case-meta").innerHTML = [
        `<span class="badge">Case: ${item.id}</span>`,
        `<span class="badge">Status: ${item.status}</span>`,
        `<span class="badge">Assertions: ${item.assertions?.failed ?? 0}/${item.assertions?.total ?? 0}</span>`
      ].join("");
      document.getElementById("case-metrics").innerHTML = `
        <p>Wall: <strong>${item.wall_ms}</strong> ms</p>
        <p>Tool calls: <strong>${item.tool_calls}</strong> • errors: <strong>${item.tool_errors}</strong></p>
        <p>Tokens in/out: <strong>${item.tokens_in ?? "n/a"}</strong> / <strong>${item.tokens_out ?? "n/a"}</strong></p>
        <p>Cost USD: <strong>${item.cost_usd ?? "n/a"}</strong> • Steps: <strong>${item.steps ?? "n/a"}</strong></p>
      `;
      const failure = item.failure_reason || "None";
      document.getElementById("case-failure").innerHTML = `<p>Failure: <strong>${failure}</strong></p>`;
      renderTrace();
    }

    function renderTrace() {
      const traceView = document.getElementById("trace-view");
      const events = traces[selectedCaseId] || [];
      const filtered = events.filter((event) => {
        if (activeTraceFilter === "all") return true;
        return event.type === activeTraceFilter;
      });
      if (!filtered.length) {
        traceView.innerHTML = "<em>No trace events to display.</em>";
        return;
      }
      traceView.innerHTML = filtered.map((event) => {
        const payload = JSON.stringify(event, null, 2);
        return `
          <div class="trace-event">
            <strong>${event.type}</strong>
            <pre>${payload}</pre>
          </div>
        `;
      }).join("");
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
    data_json = json.dumps(report_data, ensure_ascii=False).replace("</", "<\\/")
    html = Template(_REPORT_TEMPLATE).render(data_json=Markup(data_json))
    report_path = run_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path
