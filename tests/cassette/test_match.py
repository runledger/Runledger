from __future__ import annotations

from pathlib import Path

from runledger.cassette.loader import load_cassette
from runledger.cassette.match import find_match, format_mismatch_error


def _write_cassette(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                '{"tool":"search_docs","args":{"q":"reset","filters":{"a":1,"b":2}},"ok":true,"result":{"hits":[]}}',
                '{"tool":"create_issue","args":{"title":"Login issue"},"ok":false,"error":"bad request"}',
            ]
        ),
        encoding="utf-8",
    )


def test_load_cassette_and_find_match(tmp_path: Path) -> None:
    cassette_path = tmp_path / "t1.jsonl"
    _write_cassette(cassette_path)

    entries = load_cassette(cassette_path)
    assert len(entries) == 2

    match = find_match(
        entries,
        "search_docs",
        {"filters": {"b": 2, "a": 1}, "q": "reset"},
    )
    assert match is not None
    assert match.ok is True


def test_format_mismatch_error_includes_available_entries(tmp_path: Path) -> None:
    cassette_path = tmp_path / "t1.jsonl"
    _write_cassette(cassette_path)

    entries = load_cassette(cassette_path)
    message = format_mismatch_error(entries, "missing_tool", {"q": "oops"})

    assert "Requested tool: missing_tool" in message
    assert "Available entries" in message
    assert "search_docs" in message
