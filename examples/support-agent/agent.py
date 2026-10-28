"""Inspectable JSONL adapter: replace run_policy with your own refund logic."""
import json
import sys

from runledger.scenarios.agents import run_policy


def send(value):
    print(json.dumps(value), flush=True)


def main():
    start = json.loads(sys.stdin.readline())
    call_number = 0

    def call(name, args):
        nonlocal call_number
        call_number += 1
        call_id = f"adapter-{call_number}"
        send({"type": "tool_call", "name": name, "args": args, "call_id": call_id})
        result = json.loads(sys.stdin.readline())
        if result.get("type") != "tool_result" or result.get("call_id") != call_id:
            raise ValueError("Unexpected tool result")
        return result

    output = run_policy("fixed", call, start["input"])
    send({"type": "final_output", "output": output})


if __name__ == "__main__":
    main()
