from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import os
import queue
import shutil
import signal
import subprocess
import threading
import time
from typing import Deque, Mapping, Sequence

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


class AgentDeadlineExceeded(AgentProcessError):
    """The absolute case deadline elapsed, including time spent sending input."""


def _stop_process_tree(process: subprocess.Popen[str], windows_job=None) -> None:
    """Stop and reap a worker and its children before returning to the caller."""
    if os.name == "nt":
        # A Job Object retains descendants even after their parent exits.
        if windows_job is not None:
            windows_job.close()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait()


def _command_basename(program: str) -> str:
    return program.replace("\\", "/").rsplit("/", 1)[-1].lower()


def resolve_agent_command(
    command: Sequence[str], env: Mapping[str, str] | None = None
) -> list[str]:
    """Resolve bare Python aliases against the environment used to start the agent.

    An absolute executable prevents Windows from choosing the parent application's
    Python ahead of the child's PATH. Keep explicit paths, other programs, and all
    arguments untouched. Missing aliases remain unchanged for startup diagnostics.
    """
    if not command:
        return list(command)
    program = command[0]
    normalized = program.replace("\\", "/")
    if "/" in normalized:
        return list(command)
    basename = _command_basename(program)
    if basename not in {"python", "python.exe", "python3", "python3.exe"}:
        return list(command)
    environment = os.environ if env is None else env
    if os.name == "nt":
        path = next(
            (value for key, value in environment.items() if key.upper() == "PATH"), os.defpath
        )
    else:
        path = environment.get("PATH", os.defpath)
    alternate = "python3" if basename in {"python", "python.exe"} else "python"
    for candidate in (program, alternate):
        executable = shutil.which(candidate, path=path)
        if executable is not None:
            # Do not resolve symlinks: a venv launcher may point to the base Python.
            return [os.path.abspath(executable), *command[1:]]
    return list(command)


def _prefer_available_python(
    command: Sequence[str], env: Mapping[str, str] | None = None
) -> list[str]:
    """Compatibility alias for callers of the original private helper."""
    return resolve_agent_command(command, env)


def _agent_start_error(command: Sequence[str], exc: BaseException) -> AgentProcessError:
    """Turn a failed exec into an actionable error for suite.yaml authors."""
    program = command[0] if command else ""
    rendered = " ".join(command) if command else "<empty>"
    example = '["python3", "agent/agent.py"]'
    if isinstance(exc, FileNotFoundError):
        if _command_basename(program) in {"python", "python.exe"}:
            message = (
                f"Agent command not found: {program!r}. "
                "There is no 'python' executable on PATH. "
                "Ubuntu, macOS, and many pipx installs only provide python3. "
                f"Set agent_command in suite.yaml to a Python that exists, for example {example}, "
                "or re-run `runledger init --force` to regenerate the example suite."
            )
        elif program:
            message = (
                f"Agent command not found: {program!r}. "
                "RunLedger could not start the agent because that program is not on PATH "
                "and is not an existing file. "
                "Install it, or set agent_command in suite.yaml to the command that starts "
                f"your agent (for example {example})."
            )
        else:
            message = (
                "Agent command is empty. "
                "Set agent_command in suite.yaml to the program that starts your agent, "
                f"for example {example}."
            )
    elif isinstance(exc, PermissionError):
        message = (
            f"Agent command is not executable: {program!r}. {exc}. "
            "Grant execute permission, or set agent_command in suite.yaml to a program you can run."
        )
    elif isinstance(exc, ValueError):
        message = (
            "Agent command is empty or invalid. "
            "Set agent_command in suite.yaml to the program that starts your agent, "
            f"for example {example}."
        )
    else:
        message = (
            f"Failed to start agent command {rendered!r}: {exc}. "
            "Check that agent_command in suite.yaml points at an installed, runnable program."
        )
    return AgentProcessError(message, [])


class AgentProcess:
    def __init__(
        self,
        command: Sequence[str],
        timeout_s: float | None = 30.0,
        stderr_tail: int = 200,
        *,
        deadline: float | None = None,
        env: Mapping[str, str] | None = None,
    ):
        self._command = list(command)
        self._timeout_s = timeout_s
        self._stderr_tail = stderr_tail
        self._deadline = deadline
        self._env = dict(os.environ if env is None else env)
        # Python agents otherwise use the Windows ANSI codepage for pipe IO.
        self._env["PYTHONIOENCODING"] = "utf-8"
        self._process: subprocess.Popen[str] | None = None
        self._windows_job = None
        self._stderr_buffer: Deque[str] = deque(maxlen=stderr_tail)
        self._stdout_queue: queue.Queue[object] = queue.Queue()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._send_threads: list[threading.Thread] = []
        self._stdout_closed = object()

    def __enter__(self) -> "AgentProcess":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        if not self._command or not self._command[0].strip():
            raise _agent_start_error(self._command, ValueError("empty command"))
        self._command = resolve_agent_command(self._command, self._env)
        self._check_deadline()
        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=self._env,
                bufsize=1,
                start_new_session=os.name != "nt",
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
            if os.name == "nt":
                from runledger.runner.windows_job import WindowsJob
                self._windows_job = WindowsJob(int(self._process._handle))
        except OSError as exc:
            if self._process is not None:
                _stop_process_tree(self._process, self._windows_job)
                self._process = None
            raise _agent_start_error(self._command, exc) from exc
        if self._process.stdout is None or self._process.stdin is None or self._process.stderr is None:
            raise AgentProcessError("Failed to open subprocess pipes", [])
        self._process.stderr.reconfigure(errors="replace")
        # Background threads prevent blocking reads from stalling the main loop.
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def close(self) -> None:
        if self._process is None:
            return
        _stop_process_tree(self._process, self._windows_job)
        self._windows_job = None
        for thread in self._send_threads:
            thread.join(timeout=1)
        if self._stdout_thread is not None:
            self._stdout_thread.join(timeout=1)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1)
        for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
            if stream is not None:
                stream.close()
        self._process = None
        self._stdout_thread = None
        self._stderr_thread = None
        self._send_threads = []

    def _check_deadline(self) -> None:
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise AgentDeadlineExceeded("Case wall-time budget exceeded", self._stderr_tail_list())

    def _operation_timeout(self) -> float | None:
        self._check_deadline()
        if self._deadline is None:
            return self._timeout_s
        remaining = max(0.0, self._deadline - time.monotonic())
        return remaining if self._timeout_s is None else min(remaining, self._timeout_s)

    def send(self, message: ProtocolMessage | dict[str, object]) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise AgentProcessError("Agent stdin is unavailable", self._stderr_tail_list())
        timeout = self._operation_timeout()
        completed: queue.Queue[Exception | None] = queue.Queue(maxsize=1)

        def write() -> None:
            try:
                write_jsonl_line(process.stdin, message)
                process.stdin.flush()
            except Exception as exc:
                completed.put(exc)
            else:
                completed.put(None)

        thread = threading.Thread(target=write, daemon=True)
        self._send_threads = [item for item in self._send_threads if item.is_alive()]
        self._send_threads.append(thread)
        thread.start()
        try:
            error = completed.get(timeout=timeout)
        except queue.Empty:
            self._check_deadline()
            raise AgentProcessError("Timeout sending message to agent", self._stderr_tail_list())
        if error is not None:
            raise AgentProcessError(f"Failed to send agent message: {error}", self._stderr_tail_list())
        self._check_deadline()

    def recv(self) -> ProtocolMessage:
        process = self._require_process()
        if self._stdout_thread is None:
            raise AgentProcessError("Agent stdout is unavailable", self._stderr_tail_list())

        try:
            item = self._stdout_queue.get(timeout=self._operation_timeout())
        except queue.Empty:
            self._check_deadline()
            if process.poll() is not None:
                raise AgentProcessError(
                    f"Agent exited early with code {process.returncode}", self._stderr_tail_list()
                )
            raise AgentProcessError("Case timeout waiting for agent message", self._stderr_tail_list())
        self._check_deadline()
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
        try:
            self._read_stdout_messages()
        except (OSError, UnicodeError) as exc:
            self._stdout_queue.put(exc)
        finally:
            self._stdout_queue.put(self._stdout_closed)

    def _read_stdout_messages(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
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
            except json.JSONDecodeError:
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

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr_buffer.append(line.rstrip("\n"))

    def _stderr_tail_list(self) -> list[str]:
        return list(self._stderr_buffer)
