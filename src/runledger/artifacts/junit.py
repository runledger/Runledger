from __future__ import annotations

from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

from runledger.runner.models import CaseResult


def write_junit(run_dir: Path, suite_name: str, cases: Iterable[CaseResult]) -> Path:
    junit_path = run_dir / "junit.xml"
    run_dir.mkdir(parents=True, exist_ok=True)

    cases_list = list(cases)
    tests = len(cases_list)
    failures = sum(1 for case in cases_list if not case.passed)
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
                attrib={"message": case.failure.message},
            )
            failure.text = case.failure.type

    tree = ET.ElementTree(suite)
    junit_path.write_text(
        ET.tostring(tree.getroot(), encoding="unicode"),
        encoding="utf-8",
    )
    return junit_path
