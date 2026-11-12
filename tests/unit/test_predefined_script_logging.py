"""
Tests for the audit log around predefined script execution

content_execute_predefined runs an external program and injects its output as
JavaScript, so every invocation and every refusal is logged. These tests cover
the log lines; they are also the first automated coverage of the validation
chain itself, which had none.
"""

import json
import logging
import sys
import os
import stat
import subprocess

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import (
    MAX_FAILED_OUTPUT_LENGTH,
    MAX_LOGGED_ARG_LENGTH,
    FoxMCPTools,
    format_script_args_for_log,
)


class StubWebSocketServer:
    """Stands in for the WebSocket server, recording the request it was sent

    The logging tests never need a browser: they check what the server records
    before and after the injection, so the injection itself only has to return
    a well-formed response.
    """

    def __init__(self):
        self.sent_request = None
        self.sent_timeout = None

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent_request = request
        self.sent_timeout = timeout
        return {
            "type": "response",
            "data": {"result": "ok", "url": "https://example.org/"}
        }


@pytest.fixture
def run_script():
    """Return the content_execute_predefined function, wired to a stub server"""
    tools = FoxMCPTools(StubWebSocketServer())

    async def call(**kwargs):
        tool = await tools.mcp.get_tool("content_execute_predefined")
        return await tool.fn(profile_id=1, **kwargs)

    return call


@pytest.fixture
def scripts_dir(tmp_path, monkeypatch):
    """Point FOXMCP_EXT_SCRIPTS at a temporary directory and return it"""
    monkeypatch.setenv('FOXMCP_EXT_SCRIPTS', str(tmp_path))
    return tmp_path


def write_script(directory, name, body):
    """Create an executable script and return its path"""
    path = directory / name
    path.write_text(body, newline='\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class TestArgumentFormatting:

    def test_empty_args_are_named_not_blank(self):
        """An empty list must not render as an empty string in the log"""
        assert format_script_args_for_log([]) == "(no arguments)"

    def test_short_args_are_shown_in_full(self):
        assert format_script_args_for_log(['necko', 'gfx']) == "'necko', 'gfx'"

    def test_long_args_are_truncated_and_measured(self):
        """A truncated argument still reports its full length"""
        long_arg = 'x' * (MAX_LOGGED_ARG_LENGTH + 50)
        rendered = format_script_args_for_log([long_arg])

        assert '...' in rendered
        assert f"[{MAX_LOGGED_ARG_LENGTH + 50} chars]" in rendered
        assert len(rendered) < len(long_arg) + 60


class TestRefusalsAreLogged:

    @pytest.mark.asyncio
    async def test_unset_scripts_dir_is_logged(self, run_script, monkeypatch, caplog):
        monkeypatch.delenv('FOXMCP_EXT_SCRIPTS', raising=False)

        with caplog.at_level(logging.WARNING):
            result = await run_script(tab_id=1, script_name='anything.sh')

        assert 'Error' in result
        assert 'FOXMCP_EXT_SCRIPTS is not set' in caplog.text

    @pytest.mark.asyncio
    async def test_path_traversal_attempt_is_logged(self, run_script, scripts_dir, caplog):
        """The name that matters most in the log is the one trying to escape"""
        with caplog.at_level(logging.WARNING):
            result = await run_script(tab_id=1, script_name='../../etc/passwd')

        assert 'Error' in result
        assert '../../etc/passwd' in caplog.text
        assert 'path separator' in caplog.text

    @pytest.mark.asyncio
    async def test_missing_script_is_logged(self, run_script, scripts_dir, caplog):
        with caplog.at_level(logging.WARNING):
            result = await run_script(tab_id=1, script_name='absent.sh')

        assert 'Error' in result
        assert 'not found' in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.skipif(os.name == 'nt', reason='Windows has no POSIX executable permission bit')
    async def test_non_executable_script_is_logged(self, run_script, scripts_dir, caplog):
        path = scripts_dir / 'inert.sh'
        path.write_text('#!/bin/bash\necho hi\n')
        path.chmod(0o644)

        with caplog.at_level(logging.WARNING):
            result = await run_script(tab_id=1, script_name='inert.sh')

        assert 'Error' in result
        assert 'not executable' in caplog.text

    @pytest.mark.asyncio
    async def test_failing_script_logs_exit_code(self, run_script, scripts_dir, caplog):
        write_script(scripts_dir, 'broken.sh', '#!/bin/bash\necho "went wrong" >&2\nexit 3\n')

        with caplog.at_level(logging.WARNING):
            result = await run_script(tab_id=1, script_name='broken.sh')

        assert 'Error' in result
        assert 'exited 3' in caplog.text
        assert 'went wrong' in caplog.text

    @pytest.mark.asyncio
    async def test_failing_script_reply_carries_stdout(self, run_script, scripts_dir):
        """Usage text printed to stdout is what tells an agent how to call the script"""
        write_script(scripts_dir, 'picky.sh', '#!/bin/bash\necho "Usage: picky.sh <name>"\nexit 1\n')

        result = await run_script(tab_id=1, script_name='picky.sh')

        assert result == "Error: Script 'picky.sh' failed with exit code 1.\nstdout: Usage: picky.sh <name>"

    @pytest.mark.asyncio
    async def test_failing_script_reply_cuts_long_output(self, run_script, scripts_dir):
        write_script(scripts_dir, 'noisy.sh',
                     f'#!/bin/bash\nprintf "%0{MAX_FAILED_OUTPUT_LENGTH + 500}d" 0\nprintf "%0{MAX_FAILED_OUTPUT_LENGTH + 500}d" 0 >&2\nexit 2\n')

        result = await run_script(tab_id=1, script_name='noisy.sh')

        stdout_line, stderr_line = result.splitlines()[1:]
        assert stdout_line == 'stdout: ' + '0' * MAX_FAILED_OUTPUT_LENGTH + '...'
        assert stderr_line == 'stderr: ' + '0' * MAX_FAILED_OUTPUT_LENGTH + '...'

    @pytest.mark.asyncio
    async def test_silent_script_is_logged(self, run_script, scripts_dir, caplog):
        write_script(scripts_dir, 'quiet.sh', '#!/bin/bash\nexit 0\n')

        with caplog.at_level(logging.WARNING):
            result = await run_script(tab_id=1, script_name='quiet.sh')

        assert 'Error' in result
        assert 'produced no output' in caplog.text


class TestSuccessfulRunIsLogged:

    @pytest.mark.asyncio
    async def test_invocation_records_name_args_and_tab(self, run_script, scripts_dir, caplog):
        write_script(scripts_dir, 'greet.sh', '#!/bin/bash\necho "(function() { return 1; })()"\n')

        with caplog.at_level(logging.INFO):
            await run_script(
                tab_id=42,
                script_name='greet.sh',
                script_args='["necko", "hello there"]'
            )

        assert 'greet.sh' in caplog.text
        assert 'tab 42' in caplog.text
        assert "'necko'" in caplog.text
        assert "'hello there'" in caplog.text

    @pytest.mark.asyncio
    async def test_generated_javascript_is_measured_not_printed(self, run_script, scripts_dir, caplog):
        """The log records the size; the script body must stay out of it"""
        marker = 'distinctiveTokenThatMustNotAppear'
        write_script(scripts_dir, 'big.sh', f'#!/bin/bash\necho "(function() {{ var {marker} = 1; }})()"\n')

        with caplog.at_level(logging.INFO):
            await run_script(tab_id=1, script_name='big.sh')

        assert marker not in caplog.text
        assert 'bytes of JavaScript' in caplog.text

    @pytest.mark.asyncio
    async def test_completion_records_the_page_it_ran_against(self, run_script, scripts_dir, caplog):
        write_script(scripts_dir, 'done.sh', '#!/bin/bash\necho "(function() { return 1; })()"\n')

        with caplog.at_level(logging.INFO):
            await run_script(tab_id=7, script_name='done.sh')

        assert 'completed in tab 7' in caplog.text
        assert 'https://example.org/' in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["content_execute_script", "content_execute_predefined"])
async def test_script_calls_allow_time_for_consent(tool_name, scripts_dir, monkeypatch):
    """Both script entry points allow queue wait and a full approval minute."""
    browser = StubWebSocketServer()
    tools = FoxMCPTools(browser)
    kwargs = {"profile_id": 1, "tab_id": 2}
    if tool_name == "content_execute_predefined":
        write_script(scripts_dir, "consent.sh", "40+2")
        monkeypatch.setattr("server.mcp_tools.predefined_script_command", lambda path: [path])
        monkeypatch.setattr(
            "server.mcp_tools.run_predefined_script",
            lambda command, args: subprocess.CompletedProcess(command, 0, "40+2", ""),
        )
        kwargs["script_name"] = "consent.sh"
    else:
        kwargs["code"] = "40+2"
    tool = await tools.mcp.get_tool(tool_name)
    result = await tool.fn(**kwargs)
    assert "ok" in result
    assert browser.sent_request["action"] == "content.execute_script"
    assert browser.sent_request["data"]["script"] == "40+2"
    assert browser.sent_timeout == 300.0


class TestPortablePython:

    @pytest.mark.asyncio
    @pytest.mark.parametrize('suffix', ['py', 'PY'])
    async def test_readable_generator_uses_server_python_and_literal_args(
            self, scripts_dir, suffix):
        path = scripts_dir / ('generator.' + suffix)
        path.write_text(
            'import json, sys\n'
            'print(json.dumps({"python": sys.executable, "args": sys.argv[1:]}))\n'
        )
        path.chmod(0o644)
        browser = StubWebSocketServer()
        tools = FoxMCPTools(browser)
        tool = await tools.mcp.get_tool('content_execute_predefined')
        args = ['', 'two words', 'a"b', "c'd", '$HOME; $(echo injected)', '日本語', 'C:\\some path\\']

        result = await tool.fn(profile_id=1, tab_id=17, script_name=path.name,
                               script_args=json.dumps(args))

        assert 'Error' not in result
        generated = json.loads(browser.sent_request['data']['script'])
        assert generated == {'python': sys.executable, 'args': args}
        assert browser.sent_timeout == 300.0

    @pytest.mark.asyncio
    async def test_python_failure_preserves_both_streams(self, run_script, scripts_dir):
        (scripts_dir / 'broken.py').write_text(
            'import sys\nprint("usage")\nprint("diagnostic", file=sys.stderr)\nsys.exit(3)\n'
        )
        result = await run_script(tab_id=1, script_name='broken.py')
        assert 'exit code 3' in result
        assert 'stdout: usage' in result
        assert 'stderr: diagnostic' in result

    @pytest.mark.asyncio
    async def test_python_directory_is_refused(self, run_script, scripts_dir, caplog):
        (scripts_dir / 'directory.py').mkdir()
        result = await run_script(tab_id=1, script_name='directory.py')
        assert 'not a regular file' in result
        assert 'not a regular file' in caplog.text

    @pytest.mark.asyncio
    async def test_unreadable_python_is_not_listed_or_run(
            self, run_script, scripts_dir, monkeypatch, caplog):
        from server import mcp_tools

        path = scripts_dir / 'unreadable.py'
        path.write_text('print("document.title")\n')
        access = os.access
        # Model an OS read denial even when the test process has elevated access.
        monkeypatch.setattr(mcp_tools.os, 'access',
                            lambda name, mode: False if str(name) == str(path) else access(name, mode))
        assert 'unreadable.py' not in mcp_tools.describe_predefined_scripts(str(scripts_dir))
        result = await run_script(tab_id=1, script_name='unreadable.py')
        assert 'not readable' in result
        assert 'not readable' in caplog.text
