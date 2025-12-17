from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from runledger.artifacts.junit import write_junit
from runledger.artifacts.summary import write_summary
from runledger.config.models import SuiteConfig
from runledger.runner.models import CaseResult, Failure, SuiteResult


def _build_cases() -> list[CaseResult]:
    return [
        CaseResult(
            case_id="case_a",
            passed=True,
            output={"status": "ok"},
            trace=[],
            wall_ms=100,
            tool_calls=1,
            tool_errors=0,
            tool_calls_by_name={"search_docs": 1},
            tool_errors_by_name={},
            assertions_total=2,
            assertions_failed=0,
            failed_assertions=None,
            tokens_in=10,
            tokens_out=20,
            cost_usd=0.001,
            steps=2,
            replay_cassette_path="cassettes/case_a.jsonl",
            replay_cassette_sha256="abc123",
            failure=None,
        ),
        CaseResult(
            case_id="case_b",
            passed=False,
            output=None,
            trace=[],
            wall_ms=200,
            tool_calls=2,
            tool_errors=1,
            tool_calls_by_name={"search_docs": 2},
            tool_errors_by_name={"search_docs": 1},
            assertions_total=2,
            assertions_failed=1,
            failed_assertions=[{"type": "required_fields", "message": "missing field"}],
            tokens_in=20,
            tokens_out=40,
            cost_usd=0.002,
            steps=4,
            replay_cassette_path="cassettes/case_b.jsonl",
            replay_cassette_sha256="def456",
            failure=Failure(type="assertion_failed", message="missing field"),
        ),
    ]


def test_summary_and_junit_match_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_SHA", "test-sha")

    cases = _build_cases()
    suite = SuiteConfig(
        suite_name="golden",
        agent_command=["python", "agent.py"],
        mode="replay",
        cases_path="cases",
        tool_registry=["search_docs"],
    )
    suite_result = SuiteResult(
        suite_name="golden",
        cases=cases,
        passed=False,
        total_cases=2,
        passed_cases=1,
        failed_cases=1,
        success_rate=0.5,
        total_tool_calls=3,
        total_tool_errors=1,
        total_wall_ms=300,
    )
    generated_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    summary_path = write_summary(
        tmp_path,
        suite=suite,
        suite_path=Path("suite.yaml"),
        suite_result=suite_result,
        run_id="20250101-000000-abc123",
        generated_at=generated_at,
    )
    junit_path = write_junit(tmp_path, "golden", cases)

    golden_dir = Path(__file__).resolve().parents[1] / "golden"
    assert summary_path.read_text(encoding="utf-8") == (golden_dir / "summary.json").read_text(
        encoding="utf-8"
    )
    assert junit_path.read_text(encoding="utf-8") == (golden_dir / "junit.xml").read_text(
        encoding="utf-8"
    )
