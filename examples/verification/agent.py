"""Small JSONL fixture agent with explicit, reproducible regression modes."""

from __future__ import annotations

import json
import sys


def send(message: dict) -> None:
    print(json.dumps(message), flush=True)


def main() -> int:
    start = json.loads(sys.stdin.readline())
    scenario = start["input"].get("scenario", "pass")
    if scenario != "skip-tool":
        count = 2 if scenario == "extra-tool" else 1
        for index in range(count):
            send(
                {
                    "type": "tool_call",
                    "name": "search_docs",
                    "call_id": str(index),
                    "args": {"query": "password reset"},
                }
            )
            if not sys.stdin.readline():
                return 1
    output = {"category": "support"}
    if scenario != "missing-field":
        output["reply"] = "Use the password reset link on the sign-in page."
    send({"type": "final_output", "output": output})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
