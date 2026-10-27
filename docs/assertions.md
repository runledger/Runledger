# Assertions, Tool Contracts, and Budgets

## Assertions

Supported assertion types:

- `required_fields`: ensure keys exist in the final output.
- `json_schema`: validate final output against a JSON Schema file.
- `must_call`: require specific tool calls.
- `must_not_call`: forbid specific tool calls.
- `call_order`: require tools to appear in a specific order (not necessarily adjacent).

### Example

```yaml
assertions:
  - type: json_schema
    schema_path: schema.json
  - type: must_call
    tools: ["search_docs"]
```

## Budgets

Budgets are enforced as merge gates:

- `max_wall_ms`
- `max_tool_calls`
- `max_tool_errors`

`max_wall_ms` is a deadline for the whole case, including agent startup, message waits, and live tool execution. On expiry, RunLedger stops the agent and tool worker processes. `max_tool_calls` stops a case before dispatching the first call beyond the limit. `max_tool_errors` stops it as soon as the error count exceeds the limit.

In `record` and `live` modes, tools run in a separate worker process for each case so a blocked tool can be stopped. Tool module state is shared between calls within that case, but is reset between cases and is not shared with the runner process. Cancellation cannot undo a request already accepted by an external service.

### Example

```yaml
budgets:
  max_wall_ms: 20000
  max_tool_calls: 10
  max_tool_errors: 0
```
