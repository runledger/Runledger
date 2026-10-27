# Integrations (merged)

For a runnable example in this repository, follow the [mcp-agent integration guide](mcp-agent-guide.md). It uses the actual upstream Agent lifecycle with fixed model decisions and replayed tool results. The acceptance command checks ten repeat replays plus three intentional regressions. The guide documents exactly what is tested and the optional example's upstream dependency limitations.

The [developer trial guide](developer-trial.md) separates automated acceptance evidence from feedback on a developer's own integration.

## Agentic-AI-Pipeline
PR: https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24
Adds an optional RunLedger suite and CI workflow so tool calls are deterministic in PRs.

## OpenChatBI
PR: https://github.com/zhongyu09/openchatbi/pull/8
Adds a replay-only RunLedger suite wired to the agent flow and gated by a baseline.

## mcp-agent
PR: https://github.com/joshuaalpuerto/mcp-agent/pull/3
Adds a RunLedger adapter that wraps Agent.callTool for deterministic tool-call checks in CI.
