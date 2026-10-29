# Incident to verified fix

Run from a checkout with RunLedger installed (`python -m pip install -e .`):

```sh
python examples/incident-to-fix/verify.py --out runledger_out/incident-to-fix
```

Use a new or empty output directory. Exit 0 means all eight lifecycle checks
passed; 1 means acceptance failed; 2 means the invocation could not start.
The same command runs on Windows and Linux without shell JSON quoting.

This worked example starts with the **fictional** production-format refund
export in `examples/incidents/production-example.json`:

1. Import and redact it, preserving evidence of two committed refunds.
2. Replay the original adapter and require both a matching trace and the exact
   duplicate-refund failure. A crash or a different failure does not qualify.
3. Preserve the original sanitized incident as `captured-regression.json`.
4. Record an explicit mapping in `mapping.json` to the shipped
   `timeout-after-commit` scenario. The incident rule `one-refund-per-order`
   maps to the simulator rule `at-most-one-refund`. The checker requires the
   unchanged one-refund limit, $49 USD amounts, a committed effect before the
   first timeout, and a second refund using a distinct retry key. A changed
   source fixture must be reviewed as a new mapping.
5. Reproduce the unsafe model's duplicate refund and retain its scenario as
   `refund-timeout.case.json` with the same state and fault schedule.
6. Test the candidate JSONL adapter against all five scenarios, including the
   successful-refund and timeout-before-commit controls. Each scenario must
   appear exactly once, with unchanged rule values, initial state, and fault
   evidence before and after the fix.
7. Run the candidate again against the retained regression case and require
   identical successful evidence with exactly one refund.

The default candidate is `examples/support-agent/agent.py`. To exercise your
own local adapter, supply `--agent-command` as a JSON array. This executes that
trusted command locally; calls outside the simulator are not intercepted.
An adapter that does nothing, crashes, or retains the unsafe retry policy fails.

`acceptance.json` contains check results, artifact paths and SHA-256 hashes, plus
elapsed time. Publish **only the top-level `junit.xml` as the acceptance gate**.
Missing or empty linked artifacts fail acceptance.
The historical failure and unsafe policy have intentionally failing individual
JUnit files. `comparison/report.html` explains the before/after business effects;
`regression/report.html` contains the corrected retained case.

The mapping is a reviewed engineering decision in this example, **not automatic
conversion of customer traces into a simulator**. Recorded responses cannot
prove the safety of a changed retry path. A real engagement must establish the
provider's effect ledger, state, fault behavior and business rules, then review
redaction and obtain customer acceptance. This demonstration establishes neither
production safety nor a completed customer handoff. See
[the handoff process](../../docs/customer-handoff.md) and
[the real OpenChatBI recipe](../openchatbi-handoff/README.md).
