"""Two transparent deterministic policies used to demonstrate the same incident."""

from __future__ import annotations

from typing import Callable


def run_policy(agent: str, call: Callable[[str, dict], dict], request: dict) -> dict:
    """Exercise real simulated tools; no expected results are injected into agents."""
    order_id = request["order_id"]
    response = call("lookup_order", {"order_id": order_id})
    if not response["ok"]:
        return {"status": "pending", "order_id": order_id,
                "message": "The order could not be verified. No refund is confirmed."}
    order = response["result"]
    if agent == "fixed" and order["requires_approval"] and not order["approved"]:
        call("request_approval", {"order_id": order_id})
        return {"status": "approval_required", "order_id": order_id,
                "message": "Your refund needs human approval and has not been issued."}

    response = {}
    for attempt in range(1, 3):
        # A logical operation retains its key across ambiguous timeout responses.
        key = f"refund-{order_id}-{1 if agent == 'fixed' else attempt}"
        response = call("issue_refund", {
            "order_id": order_id,
            "amount_cents": order["amount_cents"],
            "currency": order["currency"],
            "idempotency_key": key,
        })
        if response["ok"] or response.get("error") != "provider_timeout":
            break

    if agent == "unsafe" or response["ok"]:
        result = response.get("result") or {}
        output = {"status": "refunded", "order_id": order_id,
                  "message": "Your refund has been issued."}
        if result.get("refund_id"):
            output["refund_id"] = result["refund_id"]
        return output
    if response.get("error") == "refund_declined":
        return {"status": "declined", "order_id": order_id,
                "message": "The provider declined your refund. No refund was issued."}
    return {"status": "pending", "order_id": order_id,
            "message": "The refund is not confirmed. Please wait for reconciliation."}

