# OpenChatBI / LangGraph incident handoff

This recipe runs OpenChatBI's existing `evals/runledger/agent/agent.py` against its
real main LangGraph. It deliberately removes the scripted `search_schema`
decision, captures the resulting failure, and restores the original trajectory.
The rule stays **`must_call: [search_schema]`** throughout. Nothing in the
OpenChatBI checkout is edited by this recipe.

This is a deliberate integration-test incident, **not customer production
evidence**. OpenChatBI's adapter supplies scripted model decisions and cassette
tool results. It replaces or disables SQL generation, retrieval implementations,
MCP, memory, context management, and the analysis sub-agent. The recipe establishes
graph construction/invocation, serial JSONL capture, and detection of this missing
tool call; it does not establish SQL accuracy or live model behavior.

## Prerequisites and run

Use Python 3.11+ in an environment with the OpenChatBI dependencies installed.
Inspect the checkout before running it: an adapter executes trusted local code,
and this workflow is not a network or filesystem sandbox.

The recipe requires RunLedger's incident `must_call` rule. **RunLedger 0.3.0 does
not include that rule.** For this source example, install this RunLedger checkout
into the same environment after installing OpenChatBI's base dependencies:

```sh
python -m pip install -e /path/to/openchatbi
python -m pip install -e /path/to/Runledger
python /path/to/Runledger/examples/openchatbi-handoff/capture.py \
  --repo-dir /path/to/openchatbi --out /path/to/new-handoff
```

With a uv-managed environment that has no pip, use `uv pip install --python
/path/to/python -e /path/to/openchatbi -e /path/to/Runledger`, then run the same
script with that Python executable. On PowerShell, put the capture command on one
line instead of using backslash continuation. `--out` must not already exist.

The inspected upstream revision is recorded in [manifest.json](manifest.json).
The script records the supplied checkout's actual Git revision and source hashes;
it does not silently update the checkout. The c21 adapter trajectory must still
be `search_schema` followed by final output, or the run fails for review. This
works with upstream's c21 case even when it has no tool assertion: the recipe
adds the invariant to its local one-case suite and leaves the source case intact.

## What the command does

1. Copies only the c21 fixture, schema, and suite configuration into
   `private-suite/`. The actual adapter and graph are loaded from `--repo-dir`.
   The suite-wide historical baseline is omitted because this is a one-case
   contract check. Existing schema assertions and budgets are retained.
2. Calls the generic `runledger verify` command with two unchanged replays, one
   skipped-schema probe, and one restored-case replay. The negative case must fail
   specifically with `must_call`, `missing: [search_schema]`, and zero tool calls.
   Both unchanged runs and the recovery must retain the same behavior hash.
3. Records four runtime receipts confirming construction of a real compiled
   LangGraph and invocation of its original `invoke` method. The bridge observes
   these calls; it does not replace graph execution with a framework stand-in.
4. Checks task boundaries and uses RunLedger's existing JSONL importer to reject
   incomplete responses, concurrent calls, unsupported events, or missing terminal
   output. It neither invents responses nor converts tool success into effects.
5. Imports the broken and recovered logs through `runledger incident import
   --format runledger` with the same rule, then checks each with `incident inspect
   --gate`: broken exits **1**, restored exits **0**. Successful imports themselves
   exit 0 even when the captured rule fails.

`acceptance.json` is written only after all checks pass. `commands.json` retains
the exact local CLI invocations and return codes. An unsuccessful command exits
nonzero; inspect its local stdout/stderr files and any partial verification
artifacts rather than interpreting a partial output directory as success.

## Review the handoff

| Path under `--out` | Evidence |
| --- | --- |
| `acceptance.json` | Overall outcome, elapsed seconds, invariant, capture completeness, recovery hash |
| `manifest.json` | Source revision and dirty status, selected-file hashes, installed/runtime versions, declared scope |
| `verification/verification/<run-id>/verification.json` | Four generic verification checks |
| `verification/verification/<run-id>/verification.junit.xml` | Aggregate CI result; expected negative is a successful verification check |
| `incidents/before/` | Imported missing-schema trace, failing rule evaluation, redaction report, HTML and JUnit |
| `incidents/after/` | New complete trace with `search_schema` and passing rule evaluation |
| `gates/before/`, `gates/after/` | Independent incident gate results |
| `runtime-receipts/` | Local provenance for actual graph construction/invocation |

The production effect ledger is **unknown**: `effects_complete` remains false and
no `business_effect` events are fabricated. Passing this tool contract makes no
claim about external side effects. A complete provider audit ledger would be a
separate intake requirement for effect-count rules.

Source hashes cover the selected suite, case, cassette, schema, adapter, and main
graph files; they are not a whole-repository integrity claim. Editable installs
can have distribution metadata older than the loaded code, so the manifest also
records RunLedger's runtime version separately. This timing is an automated
recipe runtime, not a measurement of a developer's onboarding experience.
`runledger_runtime_source` also records the actual import path and an aggregate
SHA256 of every Python source file in that package, with line endings normalized
to LF. This identifies an editable prerelease implementation more precisely than
its version string; the script checks that those sources stay unchanged during
the run.

All output is local. `private-suite/`, console files, runtime receipts, and normal
verification artifacts may contain input, tool results, local paths, and other
private information. Imported incidents undergo the standard redaction process,
but automated redaction does **not guarantee anonymity**. Review `incident.json`,
`trace.jsonl`, `redaction-report.json`, and `report.html` before choosing what to
share; additional application-specific redaction may be necessary. The script
does not upload or publish anything.

The imported failed incident has no schema-call response to replay into a new
branch. Running the fixed adapter against that exact transcript would diverge.
Here the fixed path is established by generic verification with OpenChatBI's
known-good cassette and a **new capture**, not by claiming that transcript replay
simulates an unrecorded tool response. Redaction can also change the prompt used
by this adapter's trajectory lookup; imported replay equivalence is not claimed.
