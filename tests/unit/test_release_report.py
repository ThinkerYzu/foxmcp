"""The release guard must reject incomplete suites, even if unit tests pass."""

import importlib.util
from pathlib import Path

import pytest

import test_imports

spec = importlib.util.spec_from_file_location(
    "report_guard", Path(__file__).resolve().parents[2] / "scripts/check-test-report.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.fixture
def reports(tmp_path):
    for group in ("unit", "integration"):
        directory = tmp_path / group
        directory.mkdir()
        (directory / f"test_{group}.py").touch()
        (directory / "test_imports.py").touch()
    report = tmp_path / "report.xml"
    return tmp_path, report


def test_all_modules_across_multiple_suites(reports):
    root, report = reports
    report.write_text('<testsuites><testsuite><testcase classname="unit.test_unit.Test"/>'
                      '</testsuite><testsuite><testcase classname="integration.test_integration"/>'
                      '</testsuite></testsuites>')
    guard.check_report(report, root)


def test_missing_browser_tests_cannot_hide_behind_unit_count(reports):
    root, report = reports
    # Even equal module basenames must not let unit results stand in for browser tests.
    (root / "integration/test_integration.py").rename(root / "integration/test_unit.py")
    report.write_text('<testsuite>' + '<testcase classname="unit.test_unit"/>' * 300
                      + '</testsuite>')
    with pytest.raises(ValueError, match="Missing integration"):
        guard.check_report(report, root)
    guard.check_report(report, root, "unit")


@pytest.mark.parametrize("status", ["skipped", "failure", "error"])
def test_unsuccessful_tests_are_rejected(reports, status):
    root, report = reports
    report.write_text(f'<testsuite><testcase classname="unit.test_unit"><{status}/>'
                      '</testcase></testsuite>')
    with pytest.raises(ValueError, match="Unsuccessful"):
        guard.check_report(report, root, "unit")


def test_empty_suite_is_rejected(reports):
    root, report = reports
    report.write_text('<testsuite/>')
    with pytest.raises(ValueError, match="No tests ran"):
        guard.check_report(report, root)


def test_windows_suite_has_its_own_completeness_gate(reports):
    root, report = reports
    (root / "windows").mkdir()
    (root / "windows/test_native.py").touch()
    report.write_text('<testsuite><testcase classname="windows.test_native"/></testsuite>')
    guard.check_report(report, root, "windows")
    (root / "windows/test_install.py").touch()
    with pytest.raises(ValueError, match="Missing windows.*test_install"):
        guard.check_report(report, root, "windows")
    report.write_text('<testsuite><testcase classname="windows.test_native"><skipped/>'
                      '</testcase></testsuite>')
    with pytest.raises(ValueError, match="Unsuccessful"):
        guard.check_report(report, root, "windows")
