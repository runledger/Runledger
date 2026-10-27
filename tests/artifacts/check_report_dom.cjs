const assert = require("node:assert/strict");
const fs = require("node:fs");
const { JSDOM, VirtualConsole } = require("jsdom");

const errors = [];
const virtualConsole = new VirtualConsole();
virtualConsole.on("jsdomError", (error) => errors.push(error));
const dom = new JSDOM(fs.readFileSync(process.argv[2], "utf8"), {
  runScripts: "dangerously",
  virtualConsole,
});

try {
  const { document, Event } = dom.window;
  const data = JSON.parse(document.getElementById("runledger-data").textContent);
  const hostile = data.summary.cases[0];

  // Trigger image errors explicitly: jsdom does not fetch images by default.
  for (const image of document.querySelectorAll("img")) {
    image.dispatchEvent(new Event("error"));
  }
  assert.equal(dom.window.__reportInjected, undefined);
  assert.equal(document.querySelectorAll("script").length, 2);
  assert.equal(document.querySelectorAll("img, svg, iframe, [onerror], [onload]").length, 0);
  assert.deepEqual(errors, []);
  assert.equal(document.querySelectorAll("#case-rows tr").length, 2);
  assert.equal(document.querySelector("#case-rows td").textContent, hostile.id);
  assert.equal(document.querySelector("#case-failure strong").textContent, hostile.failure_reason);
  assert.ok(document.querySelector("#meta").textContent.includes(data.summary.run.mode));
  assert.ok(document.querySelector("#kpis").textContent.includes(data.summary.aggregates.cases_pass));
  assert.ok(document.querySelector("#case-metrics").textContent.includes(hostile.wall_ms));
  assert.ok(document.querySelector("#case-meta").textContent.includes(hostile.assertions.failed));
  assert.equal(document.querySelectorAll("#trace-view .trace-event").length, 5);
  assert.deepEqual(
    JSON.parse(document.querySelector("#trace-view pre").textContent),
    data.traces[hostile.id][0],
  );

  function clickFilter(container, label) {
    const button = [...document.querySelectorAll(`${container} button`)]
      .find((item) => item.textContent === label);
    assert.ok(button, `missing filter ${label}`);
    button.click();
  }

  clickFilter("#trace-filters", "TOOL RESULT");
  assert.equal(document.querySelectorAll("#trace-view .trace-event").length, 1);
  assert.equal(document.querySelector("#trace-view strong").textContent, "tool_result");
  clickFilter("#trace-filters", "LOG");
  assert.equal(document.querySelector("#trace-view em").textContent, "No trace events to display.");
  clickFilter("#trace-filters", "ALL");
  clickFilter("#filters", "PASS");
  assert.equal(document.querySelectorAll("#case-rows tr").length, 1);
  document.querySelector("#case-rows tr").click();
  assert.ok(document.querySelector("#case-meta").textContent.includes("safe-case"));
  assert.equal(document.querySelector("#case-failure strong").textContent, "None");
  assert.equal(document.querySelectorAll("#trace-view .trace-event").length, 1);
  clickFilter("#filters", "FAIL");
  document.querySelector("#case-rows tr").click();
  assert.equal(document.querySelector("#case-failure strong").textContent, hostile.failure_reason);
  assert.equal(document.querySelectorAll("#trace-view .trace-event").length, 5);
  assert.equal(document.querySelectorAll("img, [onerror], [onload]").length, 0);
  assert.deepEqual(errors, []);
} finally {
  dom.window.close();
}
