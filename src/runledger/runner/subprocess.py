from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import queue
import subprocess
import threading
import time
from typing import Deque, Sequence

from runledger.protocol.jsonl import JsonlParseError, write_jsonl_line
from runledger.protocol.messages import ProtocolMessage, parse_message


@dataclass
class AgentProcessError(Exception):
    message: str
    stderr_tail: list[str]

    def __str__(self) -> str:
        if not self.stderr_tail:
            return self.message
        tail = "\n".join(self.stderr_tail)
        return f"{self.message}\nAgent stderr (tail):\n{tail}"


class AgentProcess:
    def __init__(self, command: Sequence[str], timeout_s: float = 30.0, stderr_tail: int = 200):
        self._command = list(command)
        self._timeout_s = timeout_s
        self._stderr_tail = stderr_tail
        self._process: subprocess.Popen[str] | None = None
        self._stderr_buffer: Deque[str] = deque(maxlen=stderr_tail)
        self._stdout_queue: queue.Queue[object] = queue.Queue()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stdout_closed = object()

    def __enter__(self) -> "AgentProcess":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self._process.stdout is None or self._process.stdin is None or self._process.stderr is None:
            raise AgentProcessError("Failed to open subprocess pipes", [])
        # Background threads prevent blocking reads from stalling the main loop.
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def close(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._stdout_thread is not None:
            self._stdout_thread.join(timeout=1)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1)
        self._process = None
        self._stdout_thread = None
        self._stderr_thread = None

    def send(self, message: ProtocolMessage | dict[str, object]) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise AgentProcessError("Agent stdin is unavailable", self._stderr_tail_list())
        write_jsonl_line(process.stdin, message)
        process.stdin.flush()

    def recv(self) -> ProtocolMessage:
        process = self._require_process()
        if self._stdout_thread is None:
            raise AgentProcessError("Agent stdout is unavailable", self._stderr_tail_list())

        deadline = time.monotonic() + self._timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgentProcessError(
                    "Case timeout waiting for agent message",
                    self._stderr_tail_list(),
                )
            try:
                item = self._stdout_queue.get(timeout=remaining)
            except queue.Empty:
                if process.poll() is not None:
                    raise AgentProcessError(
                        f"Agent exited early with code {process.returncode}",
                        self._stderr_tail_list(),
                    )
                continue
            if item is self._stdout_closed:
                raise AgentProcessError("Agent stdout closed unexpectedly", self._stderr_tail_list())
            if isinstance(item, Exception):
                raise AgentProcessError(str(item), self._stderr_tail_list()) from item
            return item

    def _require_process(self) -> subprocess.Popen[str]:
        if self._process is None:
            raise AgentProcessError("Agent process has not started", [])
        return self._process

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._stdout_queue.put(self._stdout_closed)
            return
        line_number = 0
        for line in process.stdout:
            line_number += 1
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
                message = parse_message(raw)
            except json.JSONDecodeError as exc:
                self._stdout_queue.put(
                    JsonlParseError(
                        message="Invalid JSON from agent stdout; print logs to stderr, not stdout",
                        line=stripped[:200],
                        line_number=line_number,
                    )
                )
                break
            except Exception as exc:
                self._stdout_queue.put(exc)
                break
            else:
                self._stdout_queue.put(message)
        self._stdout_queue.put(self._stdout_closed)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr_buffer.append(line.rstrip("\n"))

    def _stderr_tail_list(self) -> list[str]:
        return list(self._stderr_buffer)
