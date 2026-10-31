"""Native Windows argument handling and real bundled script execution."""

import json
from pathlib import Path

import pytest

import test_imports
from server import mcp_tools


@pytest.mark.parametrize('extension', ['py', 'sh'])
def test_real_process_preserves_arguments(tmp_path, extension):
    directory = tmp_path / 'scripts with spaces'
    directory.mkdir()
    script = directory / f'echo-args.{extension}'
    arguments = ['two words', '"quoted"', "it's literal", '$HOME; & | > < $(echo injected)', '', '--option', 'line1\nline2']
    if extension == 'py':
        body = 'import json, sys\nprint(json.dumps(sys.argv[1:]))\n'
    else:
        body = '#!/bin/bash\nprintf "%s\\0" "$@"\n'
    script.write_text(body, encoding='utf-8', newline='\n')
    command = mcp_tools.predefined_script_command(str(script))
    result = mcp_tools.run_predefined_script(command, arguments)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout) if extension == 'py' else result.stdout.split('\0')[:-1]
    assert actual == arguments


@pytest.mark.asyncio
@pytest.mark.parametrize('name,args,marker', [
    ('set-file-input.py', ['example-file', '#upload'], 'DataTransfer'),
    ('dom-summarize.sh', ['onscreen', 'withpos'], 'traverseDOM'),
])
async def test_bundled_script_reaches_browser_transport(monkeypatch, name, args, marker):
    class Browser:
        sent = None

        async def send_request_and_wait(self, request, timeout=30.0):
            self.sent = request
            return {'type': 'response', 'data': {'result': 'browser result', 'url': 'http://localhost/'}}

    scripts = Path(__file__).resolve().parents[2] / 'predefined-ex'
    monkeypatch.setenv('FOXMCP_EXT_SCRIPTS', str(scripts))
    browser = Browser()
    tool = await mcp_tools.FoxMCPTools(browser).mcp.get_tool('content_execute_predefined')
    result = await tool.fn(profile_id=1, tab_id=42, script_name=name, script_args=json.dumps(args))
    assert 'browser result' in result, result
    assert browser.sent['profile_id'] == 1
    assert browser.sent['data']['tabId'] == 42
    assert marker in browser.sent['data']['script']
