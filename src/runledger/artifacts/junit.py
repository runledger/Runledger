from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from runledger.reporting import collect_gate_failures
from runledger.runner.models import CaseResult
from runledger.util.redaction import redact_text


def write_junit(
    run_dir: Path,
    suite_name: str,
    cases: Iterable[CaseResult],
    *,
    regression: Mapping[str, Any] | None = None,
) -> Path:
    junit_path = run_dir / "junit.xml"
    run_dir.mkdir(parents=True, exist_ok=True)

    cases_list = list(cases)
    gate_failures = collect_gate_failures(regression)
    tests = len(cases_list) + len(gate_failures)
    failures = sum(1 for case in cases_list if not case.passed) + len(gate_failures)
    time_seconds = sum(case.wall_ms for case in cases_list) / 1000.0

    suite = ET.Element(
        "testsuite",
        attrib={
            "name": suite_name,
            "tests": str(tests),
            "failures": str(failures),
            "time": f"{time_seconds:.3f}",
        },
    )

    for case in cases_list:
        testcase = ET.SubElement(
            suite,
            "testcase",
            attrib={
                "name": case.case_id,
                "time": f"{case.wall_ms / 1000.0:.3f}",
            },
        )
        if case.failure is not None:
            failure = ET.SubElement(
                testcase,
                "failure",
                attrib={"message": redact_text(case.failure.message)},
            )
            failure.text = redact_text(case.failure.type)

    for gate in gate_failures:
        testcase = ET.SubElement(
            suite,
            "testcase",
            attrib={
                "name": f"regression:{gate.gate}",
                "classname": "runledger.regression",
                "time": "0.000",
            },
        )
        failure = ET.SubElement(
            testcase,
            "failure",
            attrib={"message": redact_text(gate.message), "type": "regression"},
        )
        failure.text = redact_text(gate.message)

    tree = ET.ElementTree(suite)
    junit_path.write_text(
        ET.tostring(tree.getroot(), encoding="unicode"),
        encoding="utf-8",
    )
    return junit_path
