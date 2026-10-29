"""Load OpenChatBI's real adapter; optionally remove its schema-discovery decision."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import uuid
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--skip-schema", action="store_true")
    args = parser.parse_args()
    repo = args.repo_dir.resolve()
    sys.path.insert(0, str(repo))
    path = repo / "evals/runledger/agent/agent.py"
    spec = importlib.util.spec_from_file_location("openchatbi_handoff_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the requested OpenChatBI adapter")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    import yaml

    case = yaml.safe_load(
        (repo / "evals/runledger/cases/c21_schema_discovery.yaml").read_text(encoding="utf-8")
    )
    prompt = case["input"]["prompt"]
    if adapter._TRAJECTORIES.get(prompt) != ["search_schema", None]:
        raise RuntimeError("Unsupported adapter trajectory; inspect this OpenChatBI revision")
    if args.skip_schema:
        adapter._TRAJECTORIES[prompt] = [None]

    receipt = {
        "scenario": "skip-schema" if args.skip_schema else "original",
        "adapter": str(path),
        "graph_builds": 0,
        "graph_invocations": 0,
    }
    configure = adapter._configure_agent_graph

    def configure_with_receipt(graph_module, channel):
        if Path(graph_module.__file__).resolve() != repo / "openchatbi/agent_graph.py":
            raise RuntimeError("OpenChatBI was imported from a different checkout")
        configure(graph_module, channel)
        build = graph_module.build_agent_graph_sync

        def build_with_receipt(*positional, **keywords):
            graph = build(*positional, **keywords)
            receipt["graph_builds"] += 1
            receipt["graph_source"] = str(Path(graph_module.__file__).resolve())
            receipt["compiled_graph_type"] = type(graph).__module__ + "." + type(graph).__name__
            if not type(graph).__module__.startswith("langgraph."):
                raise RuntimeError("Expected a compiled LangGraph from OpenChatBI")
            invoke = graph.invoke

            def invoke_with_receipt(*positional, **keywords):
                receipt["graph_invocations"] += 1
                return invoke(*positional, **keywords)

            graph.invoke = invoke_with_receipt
            return graph

        graph_module.build_agent_graph_sync = build_with_receipt

    adapter._configure_agent_graph = configure_with_receipt
    send = adapter.JsonlChannel.send

    def send_with_receipt(message):
        if message.get("type") == "final_output":
            if receipt["graph_builds"] != 1 or receipt["graph_invocations"] != 1:
                raise RuntimeError("Expected exactly one real graph build and invocation")
            # Write before final_output: RunLedger may stop the process immediately after it.
            destination = args.receipts / (uuid.uuid4().hex + ".json")
            destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return send(message)

    adapter.JsonlChannel.send = staticmethod(send_with_receipt)
    return adapter.main()


if __name__ == "__main__":
    raise SystemExit(main())
