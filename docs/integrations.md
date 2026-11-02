# Integrations and adoption evidence

For a runnable example in this repository, follow the [mcp-agent integration guide](mcp-agent-guide.md). It uses the actual upstream Agent lifecycle with fixed model decisions and replayed tool results. The acceptance command checks ten repeat replays plus three intentional regressions. The guide documents exactly what is tested and the optional example's upstream dependency limitations.

Three external maintainers merged RunLedger integrations. A read-only audit on **2026-10-29 UTC** also found subsequent CI use in OpenChatBI and mcp-agent. Those are concrete adoption signals; they do not establish a paid engagement or a completed onboarding trial. See the [dated adoption evidence](adoption-evidence.md) for source commits, workflow runs, and maintainer feedback.

| Integration | Merged work | Observed use after merge |
| --- | --- | --- |
| Agentic-AI-Pipeline | [PR #24](https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24), merged 2026-01-04 | One replay case and a manual-only workflow remain on `master`. GitHub returned no available runs for that workflow; automatic PR gating is not configured. |
| OpenChatBI | [PR #8](https://github.com/zhongyu09/openchatbi/pull/8), merged 2026-01-04 | The default branch retains 21 replay cases. RunLedger passed on later maintainer PRs [#60](https://github.com/zhongyu09/openchatbi/pull/60) and [#62](https://github.com/zhongyu09/openchatbi/pull/62) on 2026-10-28. |
| mcp-agent | [PR #3](https://github.com/joshuaalpuerto/mcp-agent/pull/3), merged 2026-01-08 | RunLedger passed on subsequent main changes and [documentation PR #4](https://github.com/joshuaalpuerto/mcp-agent/pull/4). The latest available run passed on 2026-02-28; the workflow remains in the default branch. |

The OpenChatBI [0.2.4 upgrade and deliberate-regression PR #61](https://github.com/zhongyu09/openchatbi/pull/61) is **open**, not merged, at the audit time. Its maintainer requested two implementation changes on 2026-10-28; those reviews are linked in the evidence record. This upgrade is separate from the already merged and subsequently used integration.

**Follow-up, 2026-10-29 04:14:35 UTC:** Both requested changes were pushed in [`919d302`](https://github.com/zhongyu09/openchatbi/commit/919d302107558dcfc7e0d5bf28433e6059f6d8d1). The [fresh RunLedger check](https://github.com/zhongyu09/openchatbi/actions/runs/40816412511) passed both replay and deliberate-regression steps. Maintainer review and merge remain pending. The evidence record preserves the original audit and documents validation separately.

The [developer trial guide](developer-trial.md) separates automated checks and upstream adoption from measured onboarding feedback. Follow-up requests were already posted to all three original PRs on 2026-10-27; the evidence record distinguishes unanswered direct requests from related maintainer review activity.
