from __future__ import annotations

from pathlib import Path

import pytest

from runledger.tools.registry import resolve_tools


def test_resolve_tools_from_custom_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = tmp_path / "custom_tools.py"
    module_path.write_text(
        "\n".join(
            [
                "def ping(args):",
                "    return {'pong': args.get('value')}",
                "",
                "TOOLS = {'ping': ping}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    registry = resolve_tools(["ping"], "custom_tools")

    assert registry["ping"].call({"value": 42}) == {"pong": 42}


def test_resolve_tools_missing_tool_raises() -> None:
    with pytest.raises(ValueError):
        resolve_tools(["missing_tool"], "runledger.tools.builtin")
