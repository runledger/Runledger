"""Docs must describe gates the runner actually enforces."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC_PATHS = [
    ROOT / "README.md",
    ROOT / "summary.md",
    ROOT / "docs" / "assertions.md",
    ROOT / "docs" / "baselines.md",
    ROOT / "docs" / "ci.md",
    ROOT / "docs" / "contracts.md",
    ROOT / "docs" / "quickstart.md",
    ROOT / "docs" / "site-quickstart.md",
    ROOT / "docs" / "troubleshooting.md",
    ROOT / "docs" / "integrations.md",
]


def _assertions_section(text: str) -> str:
    start = text.lower().find("## assertions")
    if start < 0:
        return ""
    rest = text[start + len("## assertions") :]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def test_assertions_sections_match_implemented_types() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    summary = (ROOT / "summary.md").read_text(encoding="utf-8")
    for text in (readme, summary, (ROOT / "docs" / "assertions.md").read_text(encoding="utf-8")):
        section = _assertions_section(text)
        assert section
        lowered = section.lower()
        assert "`regex`" not in lowered
        assert "`contains`" not in lowered
        assert "must_call" in lowered or "must call" in lowered
        assert "call_order" in lowered or "call order" in lowered or "ordering" in lowered


def test_docs_do_not_claim_token_or_cost_budgets() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8").lower()
        assert "max_tokens_out" not in text, path
        assert "max_cost_usd" not in text, path
        assert "costs spike" not in text, path
        assert "token/cost" not in text, path
        assert "tokens/cost" not in text, path


def test_quickstart_report_command_is_portable() -> None:
    quickstart = (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
    assert "open runledger_out/**/report.html" not in quickstart
    assert "find runledger_out -name report.html" in quickstart
