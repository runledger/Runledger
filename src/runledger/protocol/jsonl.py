from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Generator, TextIO

from .messages import ProtocolMessage, parse_message


@dataclass(frozen=True)
class JsonlParseError(Exception):
    message: str
    line: str
    line_number: int

    def __str__(self) -> str:
        return f"{self.message} (line {self.line_number}): {self.line}"


def iter_jsonl(stream: TextIO) -> Generator[ProtocolMessage, None, None]:
    for line_number, line in enumerate(stream, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise JsonlParseError(
                message="Invalid JSON from agent stdout; print logs to stderr, not stdout",
                line=stripped[:200],
                line_number=line_number,
            ) from exc
        try:
            message = parse_message(raw)
        except ValueError as exc:
            raise JsonlParseError(
                message=str(exc),
                line=stripped[:200],
                line_number=line_number,
            ) from exc
        yield message


def write_jsonl_line(stream: TextIO, payload: dict[str, object] | ProtocolMessage) -> None:
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    else:
        data = payload
    stream.write(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    stream.write("\n")
