"""
Tests for the audit log around predefined script execution

content_execute_predefined runs an external program and injects its output as
JavaScript, so every invocation and every refusal is logged. These tests cover
the log lines; they are also the first automated coverage of the validation
chain itself, which had none.
"""

import logging
import os
import stat

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import (
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

    async def send_request_and_wait(self, request):
        self.sent_request = request
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
        return await tool.fn(**kwargs)

    return call


@pytest.fixture
def scripts_dir(tmp_path, monkeypatch):
    """Point FOXMCP_EXT_SCRIPTS at a temporary directory and return it"""
    monkeypatch.setenv('FOXMCP_EXT_SCRIPTS', str(tmp_path))
    return tmp_path


def write_script(directory, name, body):
    """Create an executable script and return its path"""
    path = directory / name
    path.write_text(body)
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
