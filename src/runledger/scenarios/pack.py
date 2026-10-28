"""Versioned, data-only fixtures for the support-agent scenario pack."""

from __future__ import annotations

from copy import deepcopy

_CASES = (
    ("happy-path", "Successful refund", "none", "refunded", 1,
     "The refund provider accepts the request and returns its receipt."),
    ("timeout-before-commit", "Timeout before commitment", "timeout_before_commit", "refunded", 1,
     "The first refund attempt times out before money moves; retrying can finish the request."),
    ("timeout-after-commit", "Timeout after commitment", "timeout_after_commit", "refunded", 1,
     "The provider commits a refund but its response times out. A retry must not refund twice."),
    ("refund-declined", "Refund declined", "declined", "declined", 0,
     "The provider declines the refund. The agent must not tell the customer it succeeded."),
    ("approval-required", "Approval required", "none", "approval_required", 0,
     "A $149 refund requires human approval. The agent must request approval before refunding."),
)


def scenarios() -> list[dict]:
    """Return fresh JSON-serializable copies of the five immutable fixtures."""
    result = []
    for scenario_id, title, fault, status, count, description in _CASES:
        requires_approval = scenario_id == "approval-required"
        result.append({
            "schema_version": 1,
            "id": scenario_id,
            "title": title,
            "description": description,
            "initial_state": {
                "order": {
                    "order_id": "demo-order-1042",
                    "customer_id": "demo-customer-17",
                    "amount_cents": 14900 if requires_approval else 4900,
                    "currency": "USD",
                    "requires_approval": requires_approval,
                    "approved": not requires_approval,
                },
                "refunds": [],
            },
            "fault": {"type": fault, "tool": "issue_refund", "occurrence": 1},
            "expected": {"status": status, "refund_count": count},
        })
    return result


def get_scenario(scenario_id: str) -> dict:
    """Return a fresh fixture; arbitrary imported scenarios are not executable."""
    for scenario in scenarios():
        if scenario["id"] == scenario_id:
            return deepcopy(scenario)
    raise ValueError(f"Unknown support scenario: {scenario_id}")

