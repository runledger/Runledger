from __future__ import annotations

from typing import Any


def mock_search_docs(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("q", "")).strip()
    if not query:
        query = "unknown"
    return {
        "hits": [
            {"title": "Reset password", "snippet": f"Results for {query}: reset password"},
            {"title": "Account help", "snippet": f"Results for {query}: account access"},
        ]
    }


TOOLS = {
    "mock_search_docs": mock_search_docs,
    "search_docs": mock_search_docs,
}
