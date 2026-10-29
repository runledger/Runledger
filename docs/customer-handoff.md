# Deliver a regression gate the owner can maintain

A completed delivery covers **one repository, one CI workflow, and three named failure scenarios**. Each scenario must fail for its intended reason before the fix and pass after the fix under the same rules. The owner must be able to change a case and interpret the resulting CI failure.

Use the [handoff templates](../templates/customer-handoff/README.md) for a particular engagement. Their initial status is **pending**. A working demonstration, merged integration, sent invitation, and paid delivery are different evidence; record each separately.

## Agree the boundary before implementation

Record the application entrypoint, repository and base commit, workflow file, three scenarios, business-rule IDs, adapter boundary, expected failure, and fixed outcome. Name the person who can approve case changes and the person who can configure repository rules. List unsupported paths and every model, tool, service, or business effect that remains live.

The narrow setup scope may be offered at **$299** when the written scope is accepted. It covers an existing runnable agent and supported serial traces, three agreed cases, one workflow, evidence, and an owner walkthrough. Record the actual quote, approval, and payment status; the template is not evidence of a sale. Exporter development, new framework adapters, production infrastructure changes, broader security work, and ongoing operations require a separately accepted hardening quote. Do not quietly expand a narrow setup into that work.

Record operator hours by activity and elapsed time to the first case in the owner's application. Download time, access delays, and assisted work remain visible. A supplied example passing is not the first own-application case.

## Use the delivered revision

The new delivery helpers are source examples. Work from the checkout and commit listed in the scope record, with the intended Python environment active. Install that same checkout so the CLI and helpers agree:

```sh
python -m pip install -e .
git rev-parse HEAD
```

Record the installed RunLedger version, dependency pins, Python version, operating system, and application commit in the evidence record. Use the application environment for adapters that import its dependencies. Examples are linked below; keep their commands and output paths with the delivery rather than relying on a moving branch.

- The [incident-to-fix workflow](../examples/incident-to-fix/README.md) joins incident reproduction, fixed-policy validation, and retained CI evidence.
- The [OpenChatBI handoff recipe](../examples/openchatbi-handoff/README.md) exercises its actual application graph through the existing scripted-model and replay-tool adapter.
- The [generic verification guide](setup-verification.md) covers repeated passing runs, precise negative expectations, and recovery checks.

From the delivered repository root, use a fresh output directory:

```sh
python examples/incident-to-fix/verify.py --out "runledger_out/incident-to-fix-delivery-001"
```

The top-level `acceptance.json` and `junit.xml` describe the complete check and link its phase outputs. For the OpenChatBI recipe, activate a Python 3.11 environment containing that application's dependencies and the delivered RunLedger checkout, then supply the application checkout explicitly:

```sh
python examples/openchatbi-handoff/capture.py --repo-dir "/path/to/openchatbi" --out "runledger_out/openchatbi-handoff-001"
```

Replace the application path for your machine. Its `acceptance.json` links the verification, imported before/after incidents, gate results, and runtime receipts; `manifest.json` records the source boundary. That recipe demonstrates one schema-discovery path; neither sample alone completes a customer engagement's three agreed application scenarios.

## Demonstrate the failure and the fix

For each of the three scenarios, save the source revision, input or fixture reference, rule IDs and limits, command, exit code, structured failure, and artifact location. The before/after comparison must retain the same rule definitions and relevant fixture conditions. Review a rules diff or checksum; a passing run after removing an assertion, increasing a limit, or changing the fault is not an accepted fix.

Separate two claims:

1. **The captured incident was reproduced.** Recorded calls, responses, and terminal output matched. A reproduced business-rule violation remains a failure; a reproduction command returning zero does not make the behavior safe.
2. **The candidate fixed the tested behavior.** The candidate passes the unchanged rules in a suitable stateful fixture, test environment, or new recording with independently captured evidence. A divergence from the incident alone does not establish this.

Missing dependencies, startup errors, cassette mismatches, missing final output, and an inconclusive effect ledger do not count as the intended negative result. For effect-count rules, identify the audit source and why the ledger is complete. Keep `effects_complete: false` when that cannot be established.

The refund demonstration is fictional. The OpenChatBI recipe uses authored model decisions and recorded tool responses; it does not establish live SQL, retrieval, or production-effect correctness. For a customer delivery, replace the sample with the agreed application path and label the remaining fixed or simulated dependencies.

## Review data before sharing artifacts

The operator and data owner review the sanitized incident, JSONL, HTML, and exported evidence. Record application-specific redaction paths and the reviewer/date, including whether derived values, identifiers, freeform text, amounts, or encoded fields need additional treatment. Keep raw exports and any review notes containing sensitive data in the approved private location.

Automated redaction counts are evidence that processing ran, not approval to publish. Redaction can change model decisions, types, and derived keys; record any difference that affects replay. Sharing a sanitized bundle requires its own owner decision. Do not put raw values or an original-to-alias map into the handoff templates.

## Establish the CI gate

Save CI links for the broken and fixed revisions and the exact check name. Confirm that the broken revision fails the intended check and the fixed revision passes with the same rules. For `runledger verify`, collect only `**/verification.junit.xml` as the verification test result; raw `probe.junit.xml` files intentionally include the negative failures. Other helpers document their own aggregate JUnit file.

A workflow running on PRs is not evidence that merging is blocked. Separately inspect the relevant branch protection or ruleset, record its branch selector and exact required check context, and save a dated URL, approved screenshot, or redacted API result. State whether merge queues or bypass actors affect the result. If access is unavailable, use **required-check configuration: not verified** and leave that acceptance item pending. Do not claim it is configured from a green CI run or workflow YAML alone.

## Transfer ownership and check retention

During the walkthrough, the owner edits one application case, explains its expected failure, runs it, restores or fixes it, and reads the CI evidence. Record the resulting commit or run and whether assistance was needed. Hand over commands for adding a case, intentionally refreshing a fixture, diagnosing a failure, and reverting a mistaken change.

Record owner acceptance with its date and scope. Until then, use **owner signoff: pending**. Payment status is a separate field supported by the accepted quote and payment record; technical acceptance alone does not prove payment.

For the next two relevant PRs after delivery, record whether the gate remained enabled, whether it ran, its outcome, and any bypass or deletion. Link the PRs and check runs. Leave future rows pending until observed; a promise to keep the integration is not retention evidence. Agree any follow-up contact separately.

## Evidence that can support an external claim

The [developer trial record](developer-trial.md) tracks existing outreach and distinguishes maintainer review from measured onboarding. For a new delivery, an external proof package needs the owner's approved scope, a permitted broken/fixed example, CI links, required-check evidence, and explicit permission for any quote, company name, or screenshot. Keep unapproved material private. Report missing signoff, missing payment evidence, or unobserved retention as pending rather than filling those fields with sample results.
