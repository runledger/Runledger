# Issue-first queue (deterministic CI check)

Use this phrasing consistently:

> Deterministic CI regression check (record once, replay in CI)

Proof (merged):
- https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24
- https://github.com/zhongyu09/openchatbi/pull/8

---

## Target 1: AgentOps-AI/agentops

Proposed issue title:
Optional deterministic CI regression check for agent tools?

Proposed issue body:
Hi! I'm working on RunLedger, a small deterministic CI regression check (record once, replay in CI). It adds a tiny eval suite + workflow and does not need secrets or live tool calls. It is fully optional/removable.

If you're open to it, what's the best existing agent/example entrypoint to wire to for a minimal demo?

---

## Target 2: microsoft/autogen

Proposed issue title:
Optional deterministic CI regression check for tool-using agents?

Proposed issue body:
Hi! I'm working on RunLedger, a deterministic CI regression check (record once, replay in CI). It adds a small eval suite + workflow and stays replay-only in CI (no network, no secrets). It is fully optional/removable.

If you're open to it, what's the best existing agent/example entrypoint to wire to for a minimal demo?