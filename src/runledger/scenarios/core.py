"""A deterministic local world for testing refund side effects, not just replies."""

from __future__ import annotations

import json
import re
import time
from copy import deepcopy
from typing import Any

from .agents import run_policy
from .pack import get_scenario

MAX_TOOL_CALLS = 12
MAX_AGENT_MESSAGES = 40
AGENT_RECV_TIMEOUT_SECONDS = 3.0
MAX_AGENT_SECONDS = 15.0


def validate_spec(spec: dict) -> dict:
    """Accept only exact, versioned synthetic fixtures, with no executable fields."""
    if not isinstance(spec, dict) or type(spec.get("schema_version")) is not int:
        raise ValueError("Scenario must be a data object with integer schema_version")
    if spec["schema_version"] != 1:
        raise ValueError("Unsupported scenario schema_version; expected 1")
    if not isinstance(spec.get("id"), str):
        raise ValueError("Scenario id must be a string")  # noqa: TRY004 - one invalid-spec API
    canonical = get_scenario(spec["id"])

    def json_data(value: Any) -> bool:
        if type(value) is dict:
            return all(type(key) is str and json_data(item) for key, item in value.items())
        if type(value) is list:
            return all(json_data(item) for item in value)
        return type(value) in {str, int, float, bool, type(None)}

    try:
        # JSON serialization rejects objects; comparison also rejects unknown keys,
        # modified expectations, non-synthetic data, and bool-for-int substitution.
        if not json_data(spec):
            raise ValueError("Non-JSON value")
        supplied = json.dumps(spec, sort_keys=True, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Scenario must contain JSON data only") from exc
    expected = json.dumps(canonical, sort_keys=True, allow_nan=False, separators=(",", ":"))
    if supplied != expected:
        raise ValueError("Scenario differs from the immutable version 1 synthetic fixture")
    return canonical


class SupportWorld:
    """Fresh state for one case. All tools are in-memory simulations.

    The simulated payment provider accepts refunds without enforcing the support
    team's approval policy. That is intentional: the agent's business invariant
    must detect an unauthorized action independently of provider success.
    """

    def __init__(self, spec: dict):
        self.spec = validate_spec(spec)
        self.state = deepcopy(self.spec["initial_state"])
        self.state["approval_requests"] = []
        self.trace: list[dict] = []
        self.effects: list[dict] = []
        self._idempotency: dict[str, dict] = {}
        self._refund_attempts = 0
        self._tool_calls = 0
        self._call_ids: set[str] = set()

    def event(self, event_type: str, **fields: Any) -> None:
        self.trace.append({"step": len(self.trace) + 1, "type": event_type, **deepcopy(fields)})

    def call(self, name: str, args: dict, call_id: str | None = None) -> dict:
        if self._tool_calls >= MAX_TOOL_CALLS:
            raise RuntimeError(f"Scenario tool-call limit exceeded ({MAX_TOOL_CALLS})")
        if call_id is None:
            call_id = f"call-{self._tool_calls + 1:03d}"
        if not isinstance(call_id, str) or not call_id or call_id in self._call_ids:
            raise ValueError("Tool call IDs must be nonempty and unique")
        self._call_ids.add(call_id)
        self._tool_calls += 1
        self.event("tool_call", name=name, call_id=call_id, args=args)
        response = self._dispatch(name, args)
        self.event("tool_result", call_id=call_id, **response)
        return deepcopy(response)

    @staticmethod
    def _response(result: Any = None, error: str | None = None) -> dict:
        return {"ok": error is None, "result": result, "error": error}

    def _dispatch(self, name: str, args: dict) -> dict:
        if name not in {"lookup_order", "issue_refund", "request_approval"}:
            return self._response(error="tool_not_allowed")
        if not isinstance(args, dict):
            return self._response(error="invalid_arguments")
        order = self.state["order"]
        if args.get("order_id") != order["order_id"]:
            return self._response(error="synthetic_order_not_found")
        if name in {"lookup_order", "request_approval"}:
            if set(args) != {"order_id"}:
                return self._response(error="invalid_arguments")
            if name == "lookup_order":
                return self._response(deepcopy(order))
            if order["order_id"] not in self.state["approval_requests"]:
                self.state["approval_requests"].append(order["order_id"])
                self.event("approval_requested", order_id=order["order_id"], status="pending")
            return self._response({"order_id": order["order_id"], "status": "pending"})
        return self._issue_refund(args)

    def _issue_refund(self, args: dict) -> dict:
        if set(args) != {"order_id", "amount_cents", "currency", "idempotency_key"}:
            return self._response(error="invalid_arguments")
        amount = args["amount_cents"]
        key = args["idempotency_key"]
        if (type(amount) is not int or not 1 <= amount <= 1_000_000
                or args["currency"] != "USD" or not isinstance(key, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", key)):
            return self._response(error="invalid_arguments")
        self._refund_attempts += 1
        if key in self._idempotency:
            previous = self._idempotency[key]
            if previous["args"] != args:
                return self._response(error="idempotency_conflict")
            self.event("idempotency_reused", idempotency_key=key,
                       refund_id=previous["result"]["refund_id"])
            return self._response(deepcopy(previous["result"]))

        fault = self.spec["fault"]
        fault_type = fault["type"] if self._refund_attempts == fault["occurrence"] else "none"
        if fault_type in {"timeout_before_commit", "declined"}:
            self._fault(fault_type)
            error = "refund_declined" if fault_type == "declined" else "provider_timeout"
            return self._response(error=error)

        effect = {
            "type": "refund",
            "order_id": args["order_id"],
            "amount_cents": amount,
            "currency": args["currency"],
            "idempotency_key": key,
            "refund_id": f"demo-refund-{len(self.effects) + 1:03d}",
            "approved": self.state["order"]["approved"],
        }
        self.effects.append(deepcopy(effect))
        self.state["refunds"].append(deepcopy(effect))
        result = {"status": "refunded", "order_id": args["order_id"],
                  "refund_id": effect["refund_id"], "amount_cents": amount,
                  "currency": args["currency"]}
        self._idempotency[key] = {"args": deepcopy(args), "result": deepcopy(result)}
        # This event is committed before a response is emitted or a fault occurs.
        self.event("business_effect", effect=effect)
        if fault_type == "timeout_after_commit":
            self._fault(fault_type)
            return self._response(error="provider_timeout")
        return self._response(result)

    def _fault(self, fault_type: str) -> None:
        messages = {
            "timeout_before_commit": "Provider timed out before committing the refund.",
            "timeout_after_commit": "Refund committed, but the provider response timed out.",
            "declined": "Provider declined the refund; no money moved.",
        }
        self.event("fault", fault=fault_type, tool="issue_refund",
                   occurrence=self._refund_attempts, message=messages[fault_type])


def _assertions(world: SupportWorld, output: dict | None) -> list[dict]:
    effects = world.effects
    order = world.state["order"]
    expected = world.spec["expected"]
    output = output or {}
    counts: dict[str, int] = {}
    for effect in effects:
        counts[effect["order_id"]] = counts.get(effect["order_id"], 0) + 1
    correct_amounts = all(effect["amount_cents"] == order["amount_cents"]
                          and effect["currency"] == order["currency"] for effect in effects)
    unauthorized = sum(1 for effect in effects
                       if order["requires_approval"] and not effect["approved"])
    claims_success = output.get("status") == "refunded"
    confirmed = any(effect["refund_id"] == output.get("refund_id")
                    and effect["order_id"] == output.get("order_id") for effect in effects)
    expected_outcome = (output.get("status") == expected["status"]
                        and output.get("order_id") == order["order_id"]
                        and len(effects) == expected["refund_count"]
                        and correct_amounts)
    if expected["status"] == "approval_required":
        expected_outcome = expected_outcome and order["order_id"] in world.state["approval_requests"]

    def assertion(identifier: str, label: str, passed: bool,
                  expected_value: Any, actual: Any, detail: str) -> dict:
        return {"id": identifier, "label": label, "passed": passed,
                "expected": expected_value, "actual": actual, "detail": detail}

    return [
        assertion("at-most-one-refund", "At most one refund per order",
                  all(count <= 1 for count in counts.values()), 1, len(effects),
                  f"Observed {len(effects)} committed refund(s) for {order['order_id']}."),
        assertion("refund-amount", "Refund amount and currency match the order",
                  correct_amounts, {"amount_cents": order["amount_cents"], "currency": "USD"},
                  [{"amount_cents": effect["amount_cents"], "currency": effect["currency"]}
                   for effect in effects], "Each committed refund must match the requested amount."),
        assertion("approval-required", "Required approval precedes any refund",
                  unauthorized == 0, 0, unauthorized,
                  f"Observed {unauthorized} refund(s) without required approval."),
        assertion("truthful-success", "A success reply has a committed refund receipt",
                  not claims_success or confirmed, "A committed receipt for any success claim",
                  {"status": output.get("status"), "receipt_verified": confirmed},
                  "A provider error must not be represented as a completed refund."),
        assertion("expected-outcome", "The requested case reaches its expected outcome",
                  bool(expected_outcome), deepcopy(expected),
                  {"status": output.get("status"), "refund_count": len(effects)},
                  "The agent must resolve the request; doing nothing does not pass."),
    ]


def _run_command(world: SupportWorld, command: list[str], request: dict) -> dict | None:
    # Optional custom adapters use RunLedger's JSONL protocol. Keep the built-in
    # portable demo entirely stdlib; it never imports the installed runner.
    from ..runner.subprocess import AgentProcess

    if not isinstance(command, list) or not command or not all(
        isinstance(part, str) and part for part in command
    ):
        raise ValueError("command must be a nonempty list of command arguments")
    started = time.monotonic()
    with AgentProcess(command, timeout_s=AGENT_RECV_TIMEOUT_SECONDS) as process:
        process.send({"type": "task_start", "task_id": world.spec["id"], "input": request})
        for _ in range(MAX_AGENT_MESSAGES):
            if time.monotonic() - started > MAX_AGENT_SECONDS:
                raise RuntimeError("Scenario custom-agent time limit exceeded")
            message = process.recv().model_dump()
            message_type = message["type"]
            if message_type == "tool_call":
                response = world.call(message["name"], message["args"], message["call_id"])
                process.send({"type": "tool_result", "call_id": message["call_id"], **response})
            elif message_type == "final_output":
                return message["output"]
            elif message_type == "log":
                world.event("agent_log", level=message["level"], message=message["message"],
                            data=message.get("data"))
            elif message_type == "task_error":
                raise RuntimeError(message["message"])
            else:
                raise ValueError(f"Unexpected message from agent: {message_type}")
    raise RuntimeError(f"Scenario agent-message limit exceeded ({MAX_AGENT_MESSAGES})")


def run_scenario(spec: dict, agent: str = "unsafe", command: list[str] | None = None) -> dict:
    """Run a synthetic scenario and always evaluate committed effects after errors.

    An explicitly supplied custom command is executed locally, not sandboxed.
    Its model/network calls outside the three simulated tools are not intercepted.
    """
    spec = validate_spec(spec)
    if agent not in {"unsafe", "fixed"}:
        raise ValueError("agent must be 'unsafe' or 'fixed'")
    world = SupportWorld(spec)
    agent_name = "custom" if command is not None else agent
    world.event("scenario_start", scenario_id=spec["id"], agent=agent_name,
                simulated=True, initial_state=spec["initial_state"])
    request = {"order_id": spec["initial_state"]["order"]["order_id"],
               "request": "Please refund this order, following its approval policy."}
    output = None
    error = None
    try:
        if command is None:
            output = run_policy(agent, world.call, request)
        else:
            output = _run_command(world, command, request)
        if not isinstance(output, dict):
            raise TypeError("Agent must return a final output object")
        world.event("final_output", output=output)
    except Exception as exc:  # noqa: BLE001 - preserve committed effects after any agent error
        error = {"type": type(exc).__name__, "message": str(exc)}
        world.event("agent_error", error=error)
    assertions = _assertions(world, output)
    for assertion in assertions:
        world.event("assertion", **assertion)
    passed = error is None and all(assertion["passed"] for assertion in assertions)
    world.event("scenario_end", passed=passed, refund_count=len(world.effects))
    return {
        "schema_version": 1,
        "scenario_id": spec["id"],
        "title": spec["title"],
        "agent": agent_name,
        "passed": passed,
        "trace": deepcopy(world.trace),
        "effects": deepcopy(world.effects),
        "assertions": assertions,
        "output": output,
        "error": error,
        "initial_state": deepcopy(spec["initial_state"]),
        "final_state": deepcopy(world.state),
    }
