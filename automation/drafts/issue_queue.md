# RunLedger outreach status (developer-friendly)

## What RunLedger is
RunLedger is a CLI + GitHub Action that adds a deterministic CI check for tool-using agents.
You record tool outputs once locally, then CI reuses them so PRs fail if tool calls, outputs, contracts, or budgets change unexpectedly (no live APIs in CI).

Helpful links:
- Main repo: https://github.com/runledger/Runledger
- PyPI: https://pypi.org/project/runledger/ (v0.1.0)
- GitHub Action: runledger/Runledger@v0.1
- Demo repo: https://github.com/runledger/runledger-demo

## Current progress
- Shipping: v0.1.0 is live (PyPI + Action tag).
- Proof: 3 upstream projects have merged RunLedger as an optional CI check (links below).
- Outreach: issue-first (ask first, PR only after they say "yes").
- Active integration work: none at the moment; waiting on new approvals.

## Who is using RunLedger (merged integrations)
- Agentic-AI-Pipeline: https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24
- OpenChatBI: https://github.com/zhongyu09/openchatbi/pull/8
- mcp-agent: https://github.com/joshuaalpuerto/mcp-agent/pull/3

## Who we reached out to (org/company level)
Issue-first (we asked before sending a PR):
- LlamaIndex: https://github.com/run-llama/llama_index/issues/20448
- OpenHands: https://github.com/OpenHands/OpenHands/issues/12257
- Open Interpreter: https://github.com/openinterpreter/open-interpreter/issues/1676
- crewAI: https://github.com/crewAIInc/crewAI/issues/4174
- LangChain (LangGraph): https://github.com/langchain-ai/langgraph/issues/6649
- Griptape: https://github.com/griptape-ai/griptape/issues/2050
- OpenBMB (AgentVerse): https://github.com/OpenBMB/AgentVerse/issues/148
- Significant Gravitas (AutoGPT): https://github.com/Significant-Gravitas/AutoGPT/issues/11694

PR-first (older approach; some are blocked by CLAs or third-party preview deploy checks):
- Microsoft (Autogen, Magentic UI)
- ByteDance (deer-flow)
- Docker (compose-for-agents)
- Inngest (agent-kit)
- AgentOps (agentops)
- Truffle AI (dexto)
- DaydreamsAI (daydreams)
- ClaraVerse
- AI-QL (tuui)
- Promptulate

Active PR under review:
- None (mcp-agent merged)

## Standard issue template (copy/paste)
Title:
Optional CI check for agent behavior?

Body:
Hi! I’m working on a small optional CI check that keeps agent behavior stable. You record the expected outputs once locally, then CI reuses them (no network or secrets). It adds a tiny eval folder + workflow and is fully removable.

If you’re open to it, what’s the best existing agent/example entrypoint to wire to for a minimal demo?

## Next targets (not yet contacted issue-first)
- AgentOps-AI/agentops (note: older PR already exists)
- microsoft/autogen (note: older PR already exists; may require CLA)
- langchain-ai/langchain
- pydantic/pydantic-ai
- princeton-nlp/SWE-agent
- assafelovic/gpt-researcher
- openai/swarm
- microsoft/semantic-kernel
- letta-ai/letta (formerly MemGPT)
- camel-ai/camel
