# Three-developer RunLedger trial

Trial protocol for the pilot owner, using the published RunLedger 0.3.0 examples. Feedback requests have been sent; the measured three-developer session table remains unfilled. Automated acceptance results, maintainer review, and completed human trials are recorded separately.

## Outreach and evidence already available

Status checked on 2026-10-29 at 04:03 UTC. Three tailored follow-ups were sent on 2026-10-27 in the existing merged integration PRs:

| Project | Feedback request | Observed response or related work |
| --- | --- | --- |
| OpenChatBI | [PR #8 follow-up](https://github.com/zhongyu09/openchatbi/pull/8#issuecomment-6453241559) | No direct issue-comment reply to this request. Related [upgrade PR #61](https://github.com/zhongyu09/openchatbi/pull/61) is open and received maintainer review requesting an [explicit jsonschema dependency](https://github.com/zhongyu09/openchatbi/pull/61#discussion_r4401006127) and [negative-check execution or an explanation](https://github.com/zhongyu09/openchatbi/pull/61#discussion_r4401024343). This is actionable integration feedback. |
| mcp-agent | [PR #3 follow-up](https://github.com/joshuaalpuerto/mcp-agent/pull/3#issuecomment-6453242126) | No direct reply to this follow-up at the check time. Earlier maintainer guidance confirmed the real `Agent.callTool` integration; it is not a new measured trial result. |
| Agentic-AI-Pipeline | [PR #24 follow-up](https://github.com/hoangsonww/Agentic-AI-Pipeline/pull/24#issuecomment-6453242703) | No direct reply to this follow-up at the check time. The merged optional integration alone does not establish current use. |

The [merged integrations](integrations.md) and linked reviews establish concrete adoption or review activity at those revisions. They do not establish three completed onboarding sessions, customer payment, owner acceptance of a paid delivery, or retention in the next two PRs. Those outcomes remain pending unless their own evidence is recorded. Use the [customer handoff](customer-handoff.md) for a scoped delivery and signoff.

## Test here, then contact a small number of relevant developers

Keep local and CI verification evidence for the exact release and integration used in each session. The participant table below is intentionally empty: automated checks are not human trial results.

Use relevant existing conversations before contacting additional developers. Tailor any further invitation to a specific integration, keep the ask to a 30-minute session, and record responses. An existing follow-up is not permission for repeated reminders; send further messages only with the owner's authorization and respect the recipient's response. A public repository, package download, or automated passing run does not imply that its maintainer completed a trial or endorsed RunLedger.

## What this trial should establish

Can a developer who did not build RunLedger install it, run a real tool-using agent, and get a useful regression failure within 30 minutes? Separately measure whether they can connect one tool from their own agent. Finishing the supplied example does not count as integrating their own agent.

Recruit three developers with an existing small tool-using agent: ideally one Windows/Python user, one Linux or macOS/Python user, and one Node user. Avoid using three people who already know the protocol. Give each the same release, example, and guide. Run sessions independently so earlier participants do not coach later ones.

## Pilot-owner preparation

- Confirm `runledger==0.3.0` installs from PyPI in a clean environment and `runledger/Runledger@v0.3.0` resolves to the intended release commit.
- Pin the CLI as well as the action: set `package: runledger==0.3.0` in trial CI. An action tag alone does not pin its default PyPI installation.
- Obtain the `v0.3.0` repository checkout for the sample files; they are not installed with the CLI wheel. Record the checkout commit alongside the package version.
- Verify the commands below from the delivered project root. The real integration guide is `docs/mcp-agent-guide.md`.
- Tell participants that the example uses the real npm agent package with fixed model decisions. It exercises the agent/tool integration without measuring live-model behavior.
- Prepare one short intake sheet and a stopwatch. Do not change the guide mid-session; log corrections for the next cohort.

## Participant task: 30 minutes

Start the clock before installing. Record total elapsed time, including downloads; also record download/wait time separately.

1. **Install and run the supplied example (target: minutes 0–8).** Use a fresh Python environment and Node 22 or newer. From the project root:

   ```sh
   python -m pip install "runledger==0.3.0"
   npm --prefix examples/mcp-agent ci --ignore-scripts
   runledger run examples/mcp-agent/evals/pass --mode replay
   ```

   Record time to the first passing run and the artifact directory printed by the CLI. If your system calls Python `python3`, use that command instead.

2. **Find a real regression (target: minutes 8–13).** Run one failing suite without editing it:

   ```sh
   runledger run examples/mcp-agent/evals/missing-field --mode replay
   ```

   A nonzero exit is expected. Explain which contract failed and find the corresponding evidence in `summary.json` or `report.html`. The other supplied failures are `examples/mcp-agent/evals/wrong-order` and `examples/mcp-agent/evals/extra-tool`.

3. **Connect one of your own tools (target: minutes 13–25).** Follow the integration guide to make a single case for a small, deterministic path in your agent. Keep the scope to one tool and one assertion. Record one cassette, replay it successfully, then deliberately violate the assertion or tool contract and confirm a nonzero exit. Record time to the first passing own-agent case and first understandable own-agent failure. If this step is blocked, preserve the exact blocking instruction or error; do not substitute sample-only success.

4. **Repeat and explain (target: minutes 25–30).** Run the successful own-agent case again without live tool access. Explain what the cassette freezes, what still runs, and how to refresh an intentional change. If you only completed the example, check its repeated behavior with:

   ```sh
   python examples/mcp-agent/verify.py --repeats 10
   ```

   Submit the resulting evidence and answer the feedback questions. Stop at 30 minutes for the measured session; any later assisted completion is a separate result.

## Observation rules

Let the participant work from the guide. Answer environment or access questions, but mark the timestamp of the first implementation hint. Record both independent and assisted completion times. Capture exact confusing instructions, commands, exit codes, and failure messages; a screen recording is optional and should be agreed with the participant.

Do not treat a positive reaction as product validation. The strongest evidence is a case they keep, a failure they understand, and an intention to run it in their normal PR workflow.

## Session record

| Field | Developer A | Developer B | Developer C |
| --- | --- | --- | --- |
| Date; OS; Python; Node | | | |
| Agent/framework and tool selected | | | |
| RunLedger version; example/application commits | | | |
| First sample pass, elapsed minutes | | | |
| First sample failure understood, minutes | | | |
| First own-agent pass, minutes | | | |
| First own-agent failure understood, minutes | | | |
| Download/wait time, minutes | | | |
| First implementation hint, minutes or none | | | |
| Outcome at 30 minutes | | | |
| Blocking step and exact message | | | |
| Case/artifact reference | | | |
| Owner walkthrough: case updated and explained | | | |
| Next two relevant PRs: gate/check links or pending | | | |

Use one outcome: **own-agent success**, **sample-only success**, **assisted success**, or **blocked**. Own-agent success requires a passing cassette replay and an intentional regression that fails for the expected reason, independently within 30 minutes.

## Five feedback questions

1. Where did you stop to guess what an instruction meant?
2. Could you identify the cause of the failure without reading RunLedger's source?
3. What work did this replace in your current test setup?
4. What would stop you from keeping this case in your next PR?
5. Would you run another case next week? Which actual failure would you target?

## Decide after the cohort

- Report the three raw outcomes and times; do not claim a general conversion rate from three people.
- If all three achieve independent own-agent success, keep the scope and test a broader cohort.
- If only the sample succeeds, prioritize adapter/setup work before expanding marketing claims.
- If multiple people hit the same blocker, fix that step and rerun it with someone who has not seen the solution.
- Report retention separately: after an explicitly agreed follow-up, note whether the case remained in use. Do not count promised use as observed use.

## Optional invitation draft — do not send automatically

> I'm testing RunLedger, a small CI harness for tool-using agents. Could you spend 30 minutes trying it with one tool from an agent you already have? The session includes a supplied working example, then a small integration of your own. I'm looking for confusing steps and useful failures, not a testimonial. We'd record setup times and your feedback; no recording is needed unless you prefer it. Would that fit your work this week?
