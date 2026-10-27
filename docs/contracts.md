# Public Contracts (v0.1)

This file documents the public contracts that are considered stable for v0.1.

## Suite YAML (`suite.yaml`)

Required keys:

- `suite_name` (string)
- `agent_command` (array of strings)
- `mode` ("replay" | "record" | "live")
- `cases_path` (string)
- `tool_registry` (array of strings)

Optional keys:

- `assertions` (list)
- `budgets` (object)
- `regression` (object)
- `baseline_path` (string or null)
- `output_dir` (string or null)
- `tool_module` (string or null)

Arguments in `agent_command` that identify existing local paths are resolved against the suite directory, accepting Windows separators. Values that do not identify a path are unchanged. Inline code after `-c`, `-e`, `--eval`, or `--print`, and all arguments that follow that code, are passed through unchanged. Unknown regression threshold names are rejected so a typo cannot silently disable a gate; the documented legacy aliases remain accepted.

## Case YAML (`cases/*.yaml`)

Required keys:

- `id` (string)
- `input` (object)
- `cassette` (string)

Optional keys:

- `description` (string)
- `assertions` (list)
- `budgets` (object)

## Agent Protocol (JSONL over stdio)

Runner -> Agent:

- `task_start`
- `tool_result`

Agent -> Runner:

- `tool_call`
- `final_output`
- `log` (optional)
- `task_error` (optional)

Agents must write protocol JSON only to stdout; logs go to stderr.

Replay replaces only tool requests made through this protocol. Independent model or network calls inside the agent are outside the replay boundary. Each cassette entry is consumed once per case; repeated matching requests use their recorded entries in order and fail with a cassette mismatch when those entries are exhausted.

## Artifact formats

### `run.jsonl`

Each line is a JSON event. Event types include:

- `task_start`
- `tool_call`
- `tool_result`
- `final_output`
- `log`
- `task_error`
- `assertion_failure`
- `budget_failure`
- `case_end`

### `summary.json`

Stable fields include:

- `schema_version`
- `run` (run_id, mode, exit_status)
- `suite` (name, suite_path, agent_command)
- `aggregates` (cases_pass/fail/error, pass_rate, metrics)
- `cases[]` (per-case status, wall_ms, tool calls/errors, assertions)

### Baseline schema versioning

- `schema_version` is an integer.
- Only bump on breaking changes (rename/remove required fields or change types).
- Adding optional fields does not require a bump.
