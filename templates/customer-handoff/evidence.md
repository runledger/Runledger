# Delivery evidence — pending validation

| Provenance | Value |
| --- | --- |
| Engagement ID; operator; capture date/timezone | pending |
| Application broken/fixed commit IDs | pending |
| RunLedger version and source commit or package pin | pending |
| OS; Python/Node; dependency lockfile/hash | pending |
| Documented working directory and commands | pending |
| Private artifact index | pending |
| Fixture source and replay/model boundary | pending |

## Before/after proof

| Scenario | Rule IDs and before/after rule checksum | Broken command, exit code, exact failure | Fixed command, exit code, passing evidence | Same relevant fixture/fault conditions? |
| --- | --- | --- | --- | --- |
| pending-1 | pending | pending | pending | pending |
| pending-2 | pending | pending | pending | pending |
| pending-3 | pending | pending | pending | pending |

- Rules diff reviewed by/date: pending.
- Captured incident reproduction result, separately from its business-rule result: pending.
- Candidate validation method for any changed path: stateful fixture / test environment / new recording — pending selection and evidence.
- Effect ledger source and completeness justification, if required: pending. Otherwise record `effects_complete: false`.
- No startup error, cassette mismatch, unrelated gate, missing output, or inconclusive audit substituted for the expected failure: pending validation.
- Repeated passing behavior and post-negative recovery evidence: pending.
- Aggregate JUnit path and collector configuration: pending. For generic verification, collect only `**/verification.junit.xml`.

## Redaction review

| Review item | Evidence |
| --- | --- |
| Custom JSON Pointer paths and why needed | pending; no original values |
| Sanitized incident/trace/report reviewed | pending reviewer/date |
| Encoded, derived, freeform and identifier fields checked | pending |
| Behavior or type changes caused by redaction | pending |
| Data owner's sharing decision and permitted recipients | pending |

## CI and merge configuration

| Item | Evidence |
| --- | --- |
| Broken PR/commit and failed check URL | pending |
| Fixed PR/commit and passed check URL | pending |
| Workflow file revision; exact check context | pending |
| Target branch and matching ruleset/protection rule | not verified |
| Required-check setting evidence; reviewer; checked time | not verified |
| Merge queue/bypass behavior relevant to this repository | not verified |

A passing CI job does not establish required-check configuration. If it cannot be inspected, retain `not verified` and identify the owner action needed.

## Time and effort

| Activity | Operator hours | Elapsed minutes or timestamps | Assistance/blocker notes |
| --- | --- | --- | --- |
| Setup and dependency installation | pending | pending | pending |
| First passing own-application case | pending | pending | pending |
| First intended own-application failure | pending | pending | pending |
| Three scenarios and fix validation | pending | pending | pending |
| Redaction review; CI; walkthrough | pending | pending | pending |
| Total, including separately identified waiting time | pending | pending | pending |
