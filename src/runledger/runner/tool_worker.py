"""Private JSONL tool worker; a separate process makes live calls cancellable."""
from __future__ import annotations

from contextlib import redirect_stdout
import json
import os
import sys

from runledger.protocol.jsonl import write_jsonl_line
from runledger.tools.registry import resolve_tools


def main() -> None:
    # Keep a private copy of the protocol pipe, then redirect the actual OS
    # stdout handle too: native code and child processes do not use sys.stdout.
    protocol_out = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.SetStdHandle.argtypes = [wintypes.DWORD, wintypes.HANDLE]
        kernel.SetStdHandle.restype = wintypes.BOOL
        if not kernel.SetStdHandle(wintypes.DWORD(-11), msvcrt.get_osfhandle(sys.stderr.fileno())):
            raise ctypes.WinError(ctypes.get_last_error())
    # Tool modules may print during import as well as during a call.
    with protocol_out, redirect_stdout(sys.stderr):
        request = json.loads(sys.stdin.readline())
        try:
            config = request["input"]
            registry = resolve_tools(config["tools"], config["module"])
        except Exception as exc:
            write_jsonl_line(protocol_out, {
                "type": "tool_result", "call_id": "init", "ok": False, "error": str(exc),
            })
            protocol_out.flush()
            return
        write_jsonl_line(protocol_out, {"type": "tool_result", "call_id": "init", "ok": True})
        protocol_out.flush()
        for line in sys.stdin:
            request = json.loads(line)
            response: dict[str, object] = {
                "type": "tool_result", "call_id": request["call_id"], "ok": True,
            }
            try:
                result = registry[request["name"]].call(request["args"])
                # Validate serializability here so a bad result is a tool error.
                json.dumps(result)
                response["result"] = result
            except Exception as exc:
                response.update(ok=False, error=str(exc))
            write_jsonl_line(protocol_out, response)
            protocol_out.flush()


if __name__ == "__main__":
    main()
