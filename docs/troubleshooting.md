# Troubleshooting

## Agent printed logs to stdout

Symptoms:

- JSON parse errors
- "Protocol message must be a JSON object"

Fix:

- Write logs to stderr, not stdout.

## Cassette mismatch

Symptoms:

- "Cassette mismatch" errors in run output

Fix:

- Ensure tool name and args match cassette exactly.
- Re-record the cassette in record mode if tool args changed.

## Baseline diff failing unexpectedly

Symptoms:

- Regression checks failing without code changes

Fix:

- Verify the baseline file matches the current suite config.
- Promote a new baseline if behavior change is intentional.

## Redaction removed expected values

Symptoms:

- `[REDACTED]` appears in artifacts or cassettes

Fix:

- Avoid naming output fields with sensitive key names (token, password, api_key).
- If needed, adjust redaction rules to whitelist safe fields.
