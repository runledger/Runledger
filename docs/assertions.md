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

### Example

```yaml
budgets:
  max_wall_ms: 20000
  max_tool_calls: 10
  max_tool_errors: 0
```
