# Three-developer RunLedger trial

Draft for the pilot owner. Send only after RunLedger 0.2.4 is published and the package, action, and example have passed the release checks. No invitations have been sent.

## Test here, then contact a small number of relevant developers

Finish local and CI verification of the release and the real integration before outreach. Save actual command output as technical evidence. The participant table below is intentionally empty: automated checks are not human trial results.

Then identify three developers whose current projects actually use tool calls and PR checks. Tailor each invitation to a specific integration they could try, keep the ask to a 30-minute session, and record responses. Send only after the owner chooses the targets and authorizes the messages. A public repository, package download, or automated passing run does not imply that its maintainer has tried or endorsed RunLedger.

## What this trial should establish

Can a developer who did not build RunLedger install it, run a real tool-using agent, and get a useful regression failure within 30 minutes? Separately measure whether they can connect one tool from their own agent. Finishing the supplied example does not count as integrating their own agent.

Recruit three developers with an existing small tool-using agent: ideally one Windows/Python user, one Linux or macOS/Python user, and one Node user. Avoid using three people who already know the protocol. Give each the same release, example, and guide. Run sessions independently so earlier participants do not coach later ones.

## Pilot-owner preparation

- Confirm `runledger==0.2.4` installs from PyPI in a clean environment and `runledger/Runledger@v0.2.4` resolves to the intended release commit.
- Pin the CLI as well as the action: set `package: runledger==0.2.4` in trial CI. An action tag alone does not pin its default PyPI installation.
- Verify the commands below from the delivered project root. The real integration guide is `docs/mcp-agent-guide.md`.
- Tell participants that the example uses the real npm agent package with fixed model decisions. It exercises the agent/tool integration without measuring live-model behavior.
- Prepare one short intake sheet and a stopwatch. Do not change the guide mid-session; log corrections for the next cohort.

## Participant task: 30 minutes

Start the clock before installing. Record total elapsed time, including downloads; also record download/wait time separately.

1. **Install and run the supplied example (target: minutes 0–8).** Use a fresh Python environment and Node 22 or newer. From the project root:

   ```sh
   python -m pip install "runledger==0.2.4"
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
| RunLedger version; example commit | | | |
| First sample pass, elapsed minutes | | | |
| First sample failure understood, minutes | | | |
| First own-agent pass, minutes | | | |
| First own-agent failure understood, minutes | | | |
| Download/wait time, minutes | | | |
| First implementation hint, minutes or none | | | |
| Outcome at 30 minutes | | | |
| Blocking step and exact message | | | |
| Case/artifact reference | | | |

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
