"""Cross-platform runner for the explicit custom-agent JSONL example."""
import json
import sys
from pathlib import Path

from runledger.scenarios.cli import main

if __name__ == "__main__":
    agent = Path(__file__).with_name("agent.py").resolve()
    raise SystemExit(main(["verify", "--agent-command", json.dumps([sys.executable, str(agent)]),
                           "--out", "adapter-results"], prog="runledger scenario"))
