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
    assert broker.returncode == 0
