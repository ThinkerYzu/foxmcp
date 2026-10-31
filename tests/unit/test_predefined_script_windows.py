"""Windows interpreter selection plus real subprocess/argument regression tests."""

import json
from pathlib import Path
import sys

import pytest

import test_imports  # Automatic path setup
from server import mcp_tools


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.delenv('FOXMCP_BASH', raising=False)


def test_python_uses_server_interpreter(windows):
    path = r'C:\scripts with spaces\helper.PY'
    assert mcp_tools.predefined_script_command(path) == [sys.executable, path]


def test_posix_keeps_shebang_execution(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    assert mcp_tools.predefined_script_command('/scripts/a.py') == ['/scripts/a.py']


def test_native_executable_is_unchanged(windows):
    assert mcp_tools.predefined_script_command('helper.exe') == ['helper.exe']


def test_bash_is_found_beside_git_not_wsl(windows, monkeypatch, tmp_path):
    git = tmp_path / 'Git with spaces' / 'cmd' / 'git.exe'
    bash = git.parent.parent / 'bin' / 'bash.exe'
    bash.parent.mkdir(parents=True)
    bash.touch()
    monkeypatch.setattr(mcp_tools.shutil, 'which', lambda name: str(git) if name == 'git' else r'C:\Windows\System32\bash.exe')
    assert mcp_tools.predefined_script_command(r'C:\my scripts\a.sh') == [str(bash), '--', 'C:/my scripts/a.sh']


def test_explicit_bash_path(windows, monkeypatch, tmp_path):
    bash = tmp_path / 'custom bash.exe'
    bash.touch()
    monkeypatch.setenv('FOXMCP_BASH', str(bash))
    assert mcp_tools.predefined_script_command('a.sh') == [str(bash), '--', 'a.sh']


def test_invalid_override_is_actionable(windows, monkeypatch):
    monkeypatch.setenv('FOXMCP_BASH', 'bash --login')
    with pytest.raises(ValueError, match='absolute path'):
        mcp_tools.predefined_script_command('a.sh')


def test_missing_bash_is_actionable(windows, monkeypatch):
    monkeypatch.setattr(mcp_tools.shutil, 'which', lambda _: None)
    for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
        monkeypatch.delenv(variable, raising=False)
    with pytest.raises(ValueError, match='Install Git for Windows'):
        mcp_tools.predefined_script_command('a.sh')
