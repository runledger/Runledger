from __future__ import annotations

import json
import sys


def send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def log(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("type") == "task_start":
            ticket = msg.get("input", {}).get("ticket", "")
            send(
                {
                    "type": "tool_call",
                    "name": "search_docs",
                    "call_id": "c1",
                    "args": {"q": f"reset {ticket}".strip()},
                }
            )
        elif msg.get("type") == "tool_result":
            log("tool_result received")
            send(
                {
                    "type": "final_output",
                    "output": {
                        "category": "support",
                        "reply": "Please reset your password using the account settings page.",
                    },
                }
            )
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
