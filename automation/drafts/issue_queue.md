# Issue-first outreach queue (RunLedger)

## What RunLedger is (simple)
RunLedger is a CLI + GitHub Action that adds a deterministic CI check for tool-using agents.
You record tool outputs once locally, then CI reuses them so PRs fail when tool calls, outputs, or budgets change unexpectedly (no live APIs in CI).

## Where we are right now (current progress)
- Release: RunLedger v0.1.0 is on PyPI, and the Action is available as runledger/Runledger@v0.1.
- Proof: 2 upstream projects have merged RunLedger as an optional CI check.
- Outreach: we switched to issue-first (ask first, PR only after they say yes).
- Active integration work: mcp-agent adapter PR is open and being reviewed.

## Who is using RunLedger (merged integrations)
- Agentic-AI-Pipeline: https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24
- OpenChatBI: https://github.com/zhongyu09/openchatbi/pull/8

## Who we have reached out to (org/company level)
Issue-first (we asked before sending a PR):
- LlamaIndex (run-llama/llama_index): https://github.com/run-llama/llama_index/issues/20448
- OpenHands (OpenHands/OpenHands): https://github.com/OpenHands/OpenHands/issues/12257
- Open Interpreter (openinterpreter/open-interpreter): https://github.com/openinterpreter/open-interpreter/issues/1676
- crewAI (crewAIInc/crewAI): https://github.com/crewAIInc/crewAI/issues/4174
- LangChain - LangGraph (langchain-ai/langgraph): https://github.com/langchain-ai/langgraph/issues/6649
- Griptape (griptape-ai/griptape): https://github.com/griptape-ai/griptape/issues/2050
- OpenBMB - AgentVerse (OpenBMB/AgentVerse): https://github.com/OpenBMB/AgentVerse/issues/148
- Significant Gravitas - AutoGPT (Significant-Gravitas/AutoGPT): https://github.com/Significant-Gravitas/AutoGPT/issues/11694

PR-first (older approach; some are blocked by CLAs or third-party preview deploy checks):
- Microsoft (Autogen, Magentic-UI)
- ByteDance (deer-flow)
- Docker (compose-for-agents)
- Inngest (agent-kit)
- AgentOps (agentops)
- Truffle AI (dexto)
- DaydreamsAI (daydreams)
- ClaraVerse (ClaraVerse)
- AI-QL (tuui)
- Promptulate

Active PR under review:
- mcp-agent: https://github.com/joshuaalpuerto/mcp-agent/pull/3

---

## Standard outreach wording (copy/paste)

Title:
Optional deterministic CI check for agent/tool calls?

Body:
Hi! I'm working on RunLedger, a small deterministic CI check for agent/tool calls. You record tool outputs once locally, then CI reuses them (no network, no secrets). It adds a tiny eval suite + workflow and is optional/removable.

If you're open to it, what's the best existing agent/example entrypoint to wire to for a minimal demo?

---

## Next targets to open issues for (not yet opened)
- AgentOps-AI/agentops
- microsoft/autogen
