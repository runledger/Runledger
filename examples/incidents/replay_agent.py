"""Example of a real JSONL adapter consuming the imported tool boundary.

This deliberately unsafe retry policy reproduces the fictional captured failure.
It does not access a provider, load a bundle, or know the recorded responses.
"""
import json
import sys


def send(payload):
    print(json.dumps(payload), flush=True)


def main():
    task = json.loads(sys.stdin.readline())
    context = task["input"]
    number = 0

    def call(name, args):
        nonlocal number
        number += 1
        call_id = f"adapter-{number}"
        send({"type": "tool_call", "call_id": call_id, "name": name, "args": args})
        response = json.loads(sys.stdin.readline())
        if response.get("call_id") != call_id or response.get("type") != "tool_result":
            raise ValueError("Unexpected protocol response")
        return response

    lookup = call("lookup_order", {"order_id": context["order_id"]})
    order = lookup["result"]
    response = None
    for key in context["retry_keys"]:
        response = call("issue_refund", {"order_id": order["order_id"],
                                        "amount_cents": order["amount_cents"],
                                        "currency": order["currency"], "idempotency_key": key})
        if response["ok"]:
            break
    send({"type": "final_output", "output": {"status": "refunded", "order_id": context["order_id"],
                                               "refund_id": response["result"]["refund_id"]}})


if __name__ == "__main__":
    main()
