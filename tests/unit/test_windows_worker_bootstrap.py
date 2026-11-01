"""Portable tests for the Windows bootstrap's gate and failure handling.

Native tests/windows/test_worker.py exercises the real WMI and named events.
"""

import ctypes
import json
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server import single_instance


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    captured = []
    quote = single_instance.subprocess.list2cmdline

    def command_line(command):
        captured.append(command)
        return quote(command)

    broker = Mock()
    monkeypatch.setattr(single_instance.subprocess, 'list2cmdline', command_line)
    monkeypatch.setattr(single_instance.subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    monkeypatch.setattr(single_instance.subprocess, 'Popen', Mock(return_value=broker))
    log = tmp_path / 'worker.log'
    single_instance.spawn_windows_worker([sys.executable, 'worker.py', 'argument with spaces'], log)
    payload = json.loads(broker.stdin.write.call_args.args[0])
    command = captured[0]
    assert command[4] == payload['ready_event']
    assert payload['ready_event'].startswith('Global\\FoxMCP-worker-')
    compile(command[2], '<Windows bootstrap>', 'exec')
    return command, log


def execute_bootstrap(bootstrap, monkeypatch, kernel, target):
    command, log = bootstrap
    worker_sys = SimpleNamespace(argv=['-c', *command[3:]], path=[])
    with monkeypatch.context() as patch:
        patch.setattr(ctypes, 'WinDLL', Mock(return_value=kernel), raising=False)
        patch.setattr(ctypes, 'get_last_error', lambda: 5, raising=False)
        patch.setattr(ctypes, 'WinError', lambda code: OSError(code, 'event open failed'), raising=False)
        patch.setattr(runpy, 'run_path', target)
        patch.setitem(sys.modules, 'sys', worker_sys)
        try:
            exec(command[2], {})
        finally:
            for name in ('stdin', 'stdout', 'stderr'):
                getattr(worker_sys, name).close()
    return worker_sys


def test_bootstrap_runs_target_only_after_broker_signal(bootstrap, monkeypatch):
    kernel = Mock()
    kernel.OpenEventW.return_value = 123
    kernel.WaitForSingleObject.return_value = 0

    def run_target(path, run_name):
        kernel.WaitForSingleObject.assert_called_once_with(123, 30000)
        kernel.CloseHandle.assert_called_once_with(123)
        assert path == 'worker.py' and run_name == '__main__'

    worker = execute_bootstrap(bootstrap, monkeypatch, kernel, Mock(side_effect=run_target))
    assert worker.argv == ['worker.py', 'argument with spaces']


@pytest.mark.parametrize('wait_result', [258, 0xffffffff])
def test_bootstrap_never_runs_target_when_broker_wait_fails(bootstrap, monkeypatch, wait_result):
    kernel = Mock()
    kernel.OpenEventW.return_value = 123
    kernel.WaitForSingleObject.return_value = wait_result
    target = Mock()
    with pytest.raises(RuntimeError, match='broker did not attach'):
        execute_bootstrap(bootstrap, monkeypatch, kernel, target)
    target.assert_not_called()
    kernel.CloseHandle.assert_called_once_with(123)


def test_bootstrap_never_runs_target_when_event_cannot_open(bootstrap, monkeypatch):
    kernel = Mock()
    kernel.OpenEventW.return_value = 0
    target = Mock()
    with pytest.raises(OSError, match='event open failed'):
        execute_bootstrap(bootstrap, monkeypatch, kernel, target)
    target.assert_not_called()
    kernel.WaitForSingleObject.assert_not_called()
    kernel.CloseHandle.assert_not_called()


def test_bootstrap_preserves_nonzero_target_exit(bootstrap, monkeypatch):
    kernel = Mock()
    kernel.OpenEventW.return_value = 123
    kernel.WaitForSingleObject.return_value = 0
    with pytest.raises(SystemExit) as error:
        execute_bootstrap(bootstrap, monkeypatch, kernel, Mock(side_effect=SystemExit(7)))
    assert error.value.code == 7
    kernel.CloseHandle.assert_called_once_with(123)
