# External adoption evidence

**Audited:** 2026-10-29 04:03:58 UTC. This is a dated snapshot, not a live status page.

The audit read the three original integration PRs, default-branch files, available RunLedger Actions runs/jobs, later PR metadata, and issue/review comments. No workflow was rerun and no outreach was sent. File links below use commit SHAs; PR, review, and Actions links identify the particular evidence. GitHub can delete older runs or logs, so absence from the available history is not proof that a workflow never ran.

## What the evidence supports

| Evidence category | Observed | Limit |
| --- | --- | --- |
| Maintainer acceptance | All three original integration PRs were merged by their repository maintainers. | A merge is not a purchase, endorsement of every claim, or production deployment. |
| Continued CI use | OpenChatBI and mcp-agent have successful RunLedger runs after the original merge. | A passing workflow does not prove branch protection requires it, that it caught a real incident, or that every application path is covered. |
| Human feedback | Maintainers approved the integrations; mcp-agent requested a real Agent adapter and a version pin; OpenChatBI reviewed the upgrade with concrete changes. | This is implementation feedback, not a completed timed onboarding study or a paid testimonial. Bot comments are not counted as human feedback. |
| Paid setup, production incident, measured onboarding | Not established by the inspected public records. | Unknown does not mean none exists; these claims require separate evidence. |

## Agentic-AI-Pipeline

- **Merge:** [PR #24](https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24) merged by `hoangsonww` at **2026-01-04 04:37:35 UTC**, commit [`2025552`](https://github.com/hoangsonww/Agentic-AI-Pipeline/commit/20255522976297f2f623a3fe252ab31398003965). The maintainer [approved the PR](https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24#pullrequestreview-3624668964).
- **Audited default branch:** `master` at [`443716a`](https://github.com/hoangsonww/Agentic-AI-Pipeline/commit/443716a7d227b0d36cd73b82f134ccf00aa34185).
- **Retained implementation:** [suite](https://github.com/hoangsonww/Agentic-AI-Pipeline/blob/443716a7d227b0d36cd73b82f134ccf00aa34185/evals/runledger/suite.yaml), [one case and fixtures](https://github.com/hoangsonww/Agentic-AI-Pipeline/tree/443716a7d227b0d36cd73b82f134ccf00aa34185/evals/runledger), and [baseline](https://github.com/hoangsonww/Agentic-AI-Pipeline/blob/443716a7d227b0d36cd73b82f134ccf00aa34185/baselines/runledger-demo.json). The suite requires `web_search`, a valid output schema, and at most one tool call.
- **Workflow:** [`runledger-gate`](https://github.com/hoangsonww/Agentic-AI-Pipeline/blob/443716a7d227b0d36cd73b82f134ccf00aa34185/.github/workflows/runledger.yml) is enabled but triggers only on `workflow_dispatch`. It references `runledger/Runledger@v0.1` without a `package` pin. It does not configure automatic PR checks.
- **Available runs:** GitHub's [workflow-run endpoint](https://api.github.com/repos/hoangsonww/Agentic-AI-Pipeline/actions/workflows/220520581/runs?per_page=100) returned `total_count: 0`. No later RunLedger PR/check usages could be verified. This is retained integration evidence, not demonstrated ongoing CI execution.

## OpenChatBI

- **Merge:** [PR #8](https://github.com/zhongyu09/openchatbi/pull/8) merged by `zhongyu09` at **2026-01-04 14:40:41 UTC**, commit [`4bd5baa`](https://github.com/zhongyu09/openchatbi/commit/4bd5baaf68681b48da08013069e0271167636cd8), after [maintainer approval](https://github.com/zhongyu09/openchatbi/pull/8#pullrequestreview-3625037170).
- **Audited default branch:** `main` at [`29b04c8`](https://github.com/zhongyu09/openchatbi/commit/29b04c81e7e09500dc40cb0757df89200f321c00).
- **Retained implementation:** [21 case files](https://github.com/zhongyu09/openchatbi/tree/29b04c81e7e09500dc40cb0757df89200f321c00/evals/runledger/cases), [adapter/cassettes/schema](https://github.com/zhongyu09/openchatbi/tree/29b04c81e7e09500dc40cb0757df89200f321c00/evals/runledger), [suite](https://github.com/zhongyu09/openchatbi/blob/29b04c81e7e09500dc40cb0757df89200f321c00/evals/runledger/suite.yaml), and [baseline](https://github.com/zhongyu09/openchatbi/blob/29b04c81e7e09500dc40cb0757df89200f321c00/baselines/runledger-openchatbi.json).
- **Workflow:** [current definition](https://github.com/zhongyu09/openchatbi/blob/29b04c81e7e09500dc40cb0757df89200f321c00/.github/workflows/runledger.yml) runs on PRs to `main` and manual dispatch. Its replay job installs unpinned `runledger`; its separate LLM judge is manual-only. An unpinned installation is not evidence of an intentional upgrade to a particular release.

Two later, maintainer-authored PRs have verified successful replay jobs:

| Later change | RunLedger evidence | Job completed (UTC) |
| --- | --- | --- |
| [PR #60](https://github.com/zhongyu09/openchatbi/pull/60), analysis sub-agent failure handling; merged | [Run 40720597969](https://github.com/zhongyu09/openchatbi/actions/runs/40720597969), head `d433c12666b1e9fefe11a7c5615b852db78bc530`; replay step succeeded | 2026-10-28 15:56:40 |
| [PR #62](https://github.com/zhongyu09/openchatbi/pull/62), malformed tool-call handling; open at audit | [Run 40728427180](https://github.com/zhongyu09/openchatbi/actions/runs/40728427180), head `921d80325de8f7d3daca437047870e765d7bb826`; replay step succeeded | 2026-10-28 16:43:55 |

The latter is the latest available RunLedger run at the audit time. Both separate judge jobs were skipped, as configured for PRs; their success does not establish live-model evaluation.

**Upgrade status:** [PR #61](https://github.com/zhongyu09/openchatbi/pull/61), head `2626ff78769833931e40e06639bba97ffbbfff51`, remains **open and unmerged**. It proposes pinning 0.2.4 and verifying that skipping schema discovery fails the existing graph's contract. Its [replay workflow run](https://github.com/zhongyu09/openchatbi/actions/runs/40605878562) succeeded on 2026-10-28, but that is evidence for the proposed branch, not the default branch.

The maintainer submitted [review feedback](https://github.com/zhongyu09/openchatbi/pull/61#pullrequestreview-5683177475) at **2026-10-28 13:19:07 UTC**:

1. [Declare `jsonschema` explicitly](https://github.com/zhongyu09/openchatbi/pull/61#discussion_r4401006127) in the eval extra because the new checker imports it directly.
2. [Run the regression step with `if: always()`](https://github.com/zhongyu09/openchatbi/pull/61#discussion_r4401024343), or explain an intentional skip after replay failure.

These are substantive maintainer responses, distinct from a general feedback request.

**Follow-up, 2026-10-29 04:14:35 UTC:** Both requested changes were implemented and pushed to the existing PR in commit [`919d302`](https://github.com/zhongyu09/openchatbi/commit/919d302107558dcfc7e0d5bf28433e6059f6d8d1): the eval extra explicitly declares `jsonschema`, its lock metadata is updated, and the regression-check step uses `if: always()`. The focused local adapter tests passed (11 tests), and `uv lock --check --offline` passed without changing locked package versions.

The first local graph check imported an editable RunLedger 0.3.0 checkout despite distribution metadata saying 0.2.4, so that run was excluded from published-version evidence. A fresh environment then installed the published 0.2.4 package and verified its actual import path and runtime version, while reusing the existing OpenChatBI application dependencies read-only. Both graph probes passed: the unchanged graph called `search_schema` once, and skipping that call failed only the required-call assertion while the final output still passed its schema.

The fresh [RunLedger CI run](https://github.com/zhongyu09/openchatbi/actions/runs/40816412511), which installs `runledger==0.2.4`, completed its replay job successfully at **2026-10-29 04:14:12 UTC**. Both the full replay step and deliberate-regression step succeeded; the manual-only judge was skipped. Maintainer review and merge remain pending. This validates the proposed upgrade branch, separate from default-branch adoption.

## mcp-agent

- **Merge:** [PR #3](https://github.com/joshuaalpuerto/mcp-agent/pull/3) merged by `joshuaalpuerto` at **2026-01-08 07:13:39 UTC**, commit [`063ca98`](https://github.com/joshuaalpuerto/mcp-agent/commit/063ca989b6bbe616a47f1e611ea907d02b21fa56).
- **Audited default branch:** `main` at [`bf9585b`](https://github.com/joshuaalpuerto/mcp-agent/commit/bf9585bae3c36a54157ac77476c89392afa0514b).
- **Retained implementation:** [suite and one-case fixtures](https://github.com/joshuaalpuerto/mcp-agent/tree/bf9585bae3c36a54157ac77476c89392afa0514b/evals/runledger), [baseline](https://github.com/joshuaalpuerto/mcp-agent/blob/bf9585bae3c36a54157ac77476c89392afa0514b/baselines/runledger-demo.json), and a [PR/main-push workflow](https://github.com/joshuaalpuerto/mcp-agent/blob/bf9585bae3c36a54157ac77476c89392afa0514b/.github/workflows/runledger.yml) pinned to `runledger==0.1.0` with Node 21. This is not evidence of adopting the current RunLedger release.
- **Human implementation feedback:** The maintainer [requested an adapter using the actual Agent](https://github.com/joshuaalpuerto/mcp-agent/pull/3#pullrequestreview-3624907553), [requested version pinning](https://github.com/joshuaalpuerto/mcp-agent/pull/3#discussion_r2659512348), and [confirmed `Agent.callTool` as the integration hook](https://github.com/joshuaalpuerto/mcp-agent/pull/3#issuecomment-3709217462).
- **Subsequent maintenance:** The maintainer approved and merged [PR #4](https://github.com/joshuaalpuerto/mcp-agent/pull/4) on **2026-02-28**, adding local-use and case-authoring documentation. It was authored by Copilot and merged by the maintainer; it is not a human testimonial.

Later checks show execution after the original integration merge:

| Later change | RunLedger evidence | Job completed (UTC) |
| --- | --- | --- |
| Main change “Use global prompt,” head `653edf07b487b9123b9fc22e533d8bf3fe3e9588` | [Run 22013720839](https://github.com/joshuaalpuerto/mcp-agent/actions/runs/22013720839), success | 2026-02-14 07:47:08 |
| Documentation PR #4, head `1d6fb4295382bf8b2537c6004669b34cf88ba2ae` | [Run 22254383994, attempt 2](https://github.com/joshuaalpuerto/mcp-agent/actions/runs/22254383994/attempts/2), success | 2026-02-22 07:23:10 |
| PR #4 merged to main, head `bf9585bae3c36a54157ac77476c89392afa0514b` | [Run 22512192366](https://github.com/joshuaalpuerto/mcp-agent/actions/runs/22512192366), success; latest available run | 2026-02-28 03:16:02 |

GitHub returned the job outcomes but no retained step details for these older runs. The inspected history contains only one later PR (#4), plus the later main checks above. No more recent RunLedger execution was available, so this supports historical continued CI use rather than a claim of recent weekly activity.

## Existing outreach and next actions

Feedback was already requested on all three original PRs on **2026-10-27**:

| Repository | Sent (UTC) | Request and observed response |
| --- | --- | --- |
| Agentic-AI-Pipeline | 20:51:19 | [Existing request](https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24#issuecomment-6453242703): try a pinned upgrade/manual check and break one assertion. No later direct reply was present. |
| OpenChatBI | 20:51:15 | [Existing request](https://github.com/zhongyu09/openchatbi/pull/8#issuecomment-6453241559): try an upgrade and assess failure clarity. No direct reply on #8, but the related upgrade #61 received the maintainer review above. |
| mcp-agent | 20:51:17 | [Existing request](https://github.com/joshuaalpuerto/mcp-agent/pull/3#issuecomment-6453242126): try a pinned upgrade or integration guide and assess the failure report. No later direct reply was present. |

These requests were about 31 hours old at audit time. No duplicate invitation or general feedback draft was prepared. OpenChatBI's two requested code changes were subsequently pushed and its RunLedger check passed as recorded above; the existing PR awaits maintainer review. The other two requests need time to receive a response. The observed approvals, continued CI, and review feedback should be credited without presenting them as paid customers or completed measured onboarding trials.
