"""Exercise the real Windows worker launcher, including the venv child."""

import json
import os
import sys
import time

import pytest

import test_imports
from server.single_instance import spawn_windows_worker


def test_worker_is_hidden_and_preserves_environment(tmp_path, monkeypatch):
    probe = tmp_path / 'worker probe.py'
    receipt = tmp_path / 'worker.json'
    stop = tmp_path / 'stop'
    log = tmp_path / 'worker.log'
    monkeypatch.setenv('FOXMCP_WINDOW_PROBE', 'preserved value')
    probe.write_text(
        'import ctypes, json, os, pathlib, sys, time\n'
        'ctypes.windll.kernel32.GetConsoleWindow.restype = ctypes.c_void_p\n'
        'ctypes.windll.user32.IsWindowVisible.argtypes = [ctypes.c_void_p]\n'
        'console = ctypes.windll.kernel32.GetConsoleWindow()\n'
        'receipt, stop = map(pathlib.Path, sys.argv[1:])\n'
        'print("worker logging works", file=sys.stderr, flush=True)\n'
        'receipt.write_text(json.dumps({"pid": os.getpid(), '
        '"env": os.environ.get("FOXMCP_WINDOW_PROBE"), '
        '"visible_console": bool(ctypes.windll.user32.IsWindowVisible(console)) if console else False}))\n'
        'deadline = time.monotonic() + 15\n'
        'while not stop.exists() and time.monotonic() < deadline: time.sleep(.1)\n',
        encoding='utf-8',
    )
    broker = spawn_windows_worker([sys.executable, str(probe), str(receipt), str(stop)], log)
    try:
        deadline = time.monotonic() + 15
        while not receipt.exists() and time.monotonic() < deadline:
            assert broker.poll() is None, log.read_text()
            time.sleep(.1)
        data = json.loads(receipt.read_text())
        assert data['env'] == 'preserved value'
        assert data['visible_console'] is False, 'The worker opened a visible console'
        assert 'worker logging works' in log.read_text()
    finally:
        stop.touch()
        broker.wait(timeout=20)
    assert broker.returncode == 0, log.read_text()


@pytest.fixture
def delayed_attachment(monkeypatch):
    """Expose the PID race without relying on a busy hosted runner."""
    from server import single_instance

    original = single_instance.subprocess.Popen

    def delayed(command, *args, **kwargs):
        command = list(command)
        marker = '$worker = [Diagnostics.Process]::GetProcessById($created.ProcessId)'
        assert command[-1].count(marker) == 1
        command[-1] = command[-1].replace(marker, 'Start-Sleep -Seconds 2\n' + marker)
        return original(command, *args, **kwargs)

    monkeypatch.setattr(single_instance.subprocess, 'Popen', delayed)


@pytest.mark.parametrize(('statement', 'exit_code'), [
    pytest.param('pass', 0, id='success'),
    pytest.param('raise SystemExit(7)', 7, id='system-exit'),
    pytest.param('raise RuntimeError("worker startup failed")', 1, id='startup-exception'),
])
def test_delayed_broker_preserves_immediate_worker_exit(
        tmp_path, delayed_attachment, statement, exit_code):
    probe = tmp_path / 'quick worker.py'
    log = tmp_path / 'worker.log'
    probe.write_text(
        'import sys\nprint("quick worker ran", file=sys.stderr, flush=True)\n'
        + statement + '\n', encoding='utf-8')
    broker = spawn_windows_worker([sys.executable, str(probe)], log)
    assert broker.wait(timeout=30) == exit_code, log.read_text()
    assert 'quick worker ran' in log.read_text()
    assert 'GetProcessById' not in log.read_text()
    if exit_code == 1:
        assert 'RuntimeError: worker startup failed' in log.read_text()


def test_worker_survives_broker_termination(tmp_path):
    probe = tmp_path / 'independent worker.py'
    heartbeat = tmp_path / 'heartbeat'
    stop = tmp_path / 'stop'
    done = tmp_path / 'done'
    log = tmp_path / 'worker.log'
    probe.write_text(
        'import pathlib, sys, time\n'
        'heartbeat, stop, done = map(pathlib.Path, sys.argv[1:])\n'
        'deadline = time.monotonic() + 30\n'
        'counter = 0\n'
        'try:\n'
        '    while not stop.exists() and time.monotonic() < deadline:\n'
        '        counter += 1\n'
        '        heartbeat.write_text(str(counter))\n'
        '        time.sleep(.1)\n'
        'finally:\n'
        '    done.touch()\n', encoding='utf-8')
    broker = spawn_windows_worker(
        [sys.executable, str(probe), str(heartbeat), str(stop), str(done)], log)

    def counter():
        try:
            return int(heartbeat.read_text())
        except (OSError, ValueError):
            return 0

    try:
        deadline = time.monotonic() + 15
        while not counter() and time.monotonic() < deadline:
            assert broker.poll() is None, log.read_text()
            time.sleep(.1)
        assert counter() > 0, log.read_text()
        broker.kill()
        broker.wait(timeout=10)
        # Ignore heartbeats written before the broker actually terminated.
        before = counter()
        deadline = time.monotonic() + 5
        while counter() <= before and time.monotonic() < deadline:
            time.sleep(.1)
        assert counter() > before, 'Killing the broker killed the WMI-owned worker'
    finally:
        stop.touch()
        if broker.poll() is None:
            broker.kill()
            broker.wait(timeout=10)
        deadline = time.monotonic() + 5
        while not done.exists() and time.monotonic() < deadline:
            time.sleep(.1)
        assert done.exists(), 'Worker did not finish after cleanup requested shutdown'
