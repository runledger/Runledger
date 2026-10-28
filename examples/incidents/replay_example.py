"""Cross-platform incident import/replay without shell JSON quoting."""
import json
import sys
from pathlib import Path

from runledger.incidents.cli import main

if __name__ == "__main__":
    source = Path(__file__).with_name("production-example.json").resolve()
    adapter = Path(__file__).with_name("replay_agent.py").resolve()
    code = main(["import", str(source), "--out", "incident-example-imported"])
    if code:
        raise SystemExit(code)
    raise SystemExit(main(["replay", "incident-example-imported/incident.json", "--agent-command",
                           json.dumps([sys.executable, str(adapter)]), "--out", "incident-example-replayed"]))
