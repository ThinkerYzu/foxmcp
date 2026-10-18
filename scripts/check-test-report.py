#!/usr/bin/env python3
"""Reject failed/skipped tests and missing test modules in a JUnit report."""

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


def check_report(report, tests_root, kind="all"):
    cases = list(ET.parse(report).getroot().iter("testcase"))
    if not cases:
        raise ValueError("No tests ran")
    reported_modules = set()
    for case in cases:
        parts = case.get("classname", "").split(".")
        reported_modules.update(zip(parts, parts[1:]))
        if any(case.find(tag) is not None for tag in ("skipped", "failure", "error")):
            raise ValueError(f"Unsuccessful test: {case.get('classname')}.{case.get('name')}")
    groups = ("unit", "integration") if kind == "all" else (kind,)
    for group in groups:
        modules = {path.stem for path in (tests_root / group).glob("test_*.py")
                   if path.name != "test_imports.py"}
        if not modules:
            raise ValueError(f"No {group} test modules found")
        missing = {module for module in modules if (group, module) not in reported_modules}
        if missing:
            raise ValueError(f"Missing {group} test modules: {', '.join(sorted(missing))}")
    print(f"Verified {len(cases)} passing tests; all required {', '.join(groups)} modules ran")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--kind", choices=("all", "unit"), default="all")
    args = parser.parse_args()
    try:
        check_report(args.report, Path(__file__).resolve().parents[1] / "tests", args.kind)
    except (OSError, ValueError, ET.ParseError) as error:
        parser.exit(1, f"{error}\n")
