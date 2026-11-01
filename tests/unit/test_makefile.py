"""Exercise developer commands in disposable checkouts without real services."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import test_imports


MAKEFILE = Path(__file__).resolve().parents[2] / "Makefile"


def executable(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n" + body)
    path.chmod(0o755)


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout with spaces"
    root.mkdir()
    (root / "Makefile").write_text(MAKEFILE.read_text())
    for directory in ("tests/unit", "tests/integration"):
        (root / directory).mkdir(parents=True)
    (root / "tests/test_imports.py").touch()
    return root


def run_make(root, *args, check=True):
    result = subprocess.run(
        ["make", "--no-print-directory", *args], cwd=root,
        text=True, capture_output=True, timeout=20,
        env={key: value for key, value in os.environ.items()
             if key not in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES",
                            "GNUMAKEFLAGS", "MAKEFILES", "VENV_BIN", "VENV_PIP",
                            "VENV_PYTHON", "VENV_DIR", "PYTHON", "FIREFOX_PATH")},
    )
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def replace_target(root, target, recipe):
    path = root / "Makefile"
    text, count = re.subn(
        rf"^{re.escape(target)}:[^\n]*\n(?:\t[^\n]*\n|\n)*",
        lambda _: f"{target}:\n\t{recipe}\n\n",
        path.read_text(), flags=re.MULTILINE,
    )
    assert count == 1
    path.write_text(text)


@pytest.mark.parametrize("target,stages", [
    ("all", ["setup", "test"]),
    ("ci", ["clean", "setup", "lint", "test"]),
    ("check", ["lint", "test"]),
    ("quick-test", ["build", "test-unit"]),
])
def test_aggregate_stages_are_sequential_under_parallel_make(checkout, target, stages):
    # Keep the real aggregate target; replace its stages with delayed probes.
    executable(checkout / "probe", """
import json, sys, time
from pathlib import Path
log = Path('events.jsonl')
def record(event):
    with log.open('a') as stream:
        stream.write(json.dumps([sys.argv[1], event]) + '\\n')
record('start')
time.sleep(0.05)
record('end')
""")
    for stage in ("clean", "setup", "lint", "test", "package", "build", "test-unit"):
        replace_target(checkout, stage, f"@./probe {stage}")
    run_make(checkout, "-j8", target)
    events = [json.loads(line) for line in (checkout / "events.jsonl").read_text().splitlines()]
    assert events == [[stage, event] for stage in stages for event in ("start", "end")]


@pytest.mark.parametrize("target,mode", [
    ("test-unit", ["unit"]), ("test-integration", ["integration"]), ("run-tests", []),
])
@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("inherited", [False, True])
def test_tests_use_selected_interpreter_and_preserve_firefox_path(
        checkout, target, mode, custom, inherited, monkeypatch):
    if inherited:
        monkeypatch.setenv("VENV_BIN", "/nonexistent-parent-venv/bin")
        monkeypatch.setenv("VENV_PYTHON", "/nonexistent-parent-venv/bin/python")
        monkeypatch.setenv("FIREFOX_PATH", "/nonexistent-parent-firefox")
    bin_dir = checkout / ("custom/bin" if custom else "venv/bin")
    executable(bin_dir / "python", """
import json, os, sys
from pathlib import Path
Path('invocation.json').write_text(json.dumps({
    'executable': sys.argv[0], 'args': sys.argv[1:],
    'firefox': os.environ['FIREFOX_PATH'],
}))
""")
    replace_target(checkout, "package", "@true")
    # A real file with the target's name must not suppress a phony target.
    (checkout / target).touch()
    firefox = "/opt/Firefox Developer Edition/firefox"
    args = [target, f"FIREFOX_PATH={firefox}"]
    if custom:
        args.append("VENV_BIN=custom/bin")
    run_make(checkout, *args)
    invocation = json.loads((checkout / "invocation.json").read_text())
    assert Path(invocation['executable']) == bin_dir / "python"
    assert invocation['args'] == ["tests/run_tests.py", *mode]
    assert invocation['firefox'] == firefox


def test_custom_virtualenv_is_created_and_used_for_install(checkout):
    executable(checkout / "create-venv", """
import sys
from pathlib import Path
assert sys.argv[1:3] == ['-m', 'venv']
destination = Path(sys.argv[3])
(destination / 'bin').mkdir(parents=True)
(destination / 'bin/python').touch()
pip = destination / 'bin/pip'
pip.write_text('#!/bin/sh\\nprintf "%s\\n" "$@" > pip-args\\n')
pip.chmod(0o755)
Path('created-at').write_text(str(destination))
""")
    run_make(checkout, "install", "VENV_BIN=custom/bin", "PYTHON=./create-venv")
    assert (checkout / "created-at").read_text() == str(checkout / "custom")
    assert (checkout / "pip-args").read_text().splitlines() == [
        "install", "-r", "server/requirements.txt",
    ]
    assert not (checkout / "venv").exists()


@pytest.mark.parametrize("target", ["stop", "restart"])
def test_unmanaged_process_stop_targets_are_unavailable(checkout, target):
    # Any attempted signal command fails the check instead of touching processes.
    executable(checkout / "pkill", "raise AssertionError('unexpected process signal')\n")
    result = run_make(checkout, target, f"PATH={checkout}:{os.environ['PATH']}", check=False)
    assert result.returncode != 0
    assert "No rule to make target" in result.stderr
