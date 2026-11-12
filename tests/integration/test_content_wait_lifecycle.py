"""Real Firefox wait deadlines, consent transitions and subsequent MCP HTTP calls."""

import json
from pathlib import Path
from types import SimpleNamespace
import uuid
import zipfile

from fastmcp import Client
import pytest
import pytest_asyncio

import test_imports  # noqa: F401
from test_config import profile_connection
from test_file_loading import upload_page, open_fixture, browser_request  # noqa: F401


# Appended only to a temporary test XPI. It observes the real gate and supplies
# remembered approval decisions; it does not replace injection or deadline logic.
TEST_CONTROLS = r"""
(() => {
  const handleTest = handleTestAction;
  handleTestAction = async (id, action, data) => {
    if (!action.startsWith('test.wait.')) return handleTest(id, action, data);
    try {
      if (action === 'test.wait.configure') {
        scriptConsent.configure(data.enabled);
      } else if (action === 'test.wait.remember') {
        const tab = await browser.tabs.get(data.tabId);
        scriptConsent.decisions.set(tab.id,
          {origin: scriptConsent.origin(tab.url), allowed: true});
      } else if (action === 'test.wait.run') {
        const result = await scriptConsent.run(id, data.tabId, data.script,
          {deadline: Date.now() + data.timeoutMs});
        sendResponse(id, action, {result});
        return;
      } else if (action !== 'test.wait.state') {
        throw new Error('Unknown wait test control');
      }
      sendResponse(id, action, {enabled: scriptConsent.enabled,
        transition: scriptConsent.transition, prompt: Boolean(scriptConsent.current),
        jobs: [...scriptConsent.jobs.values()].map(job =>
          ({id: job.id, tabId: job.tabId, state: job.state, deferred: job.deferred}))});
    } catch (error) { sendError(id, error.code || 'API_ERROR', error.message); }
  };
})();
"""


@pytest.fixture
def firefox_extension(tmp_path):
    root = Path(__file__).resolve().parents[2]
    source = root / 'dist/packages/foxmcp@codemud.org.xpi'
    assert source.exists(), 'Run make package first'
    target = tmp_path / 'wait-lifecycle-test.xpi'
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, 'w') as custom:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == 'manifest.json':
                manifest = json.loads(data)
                manifest['background']['scripts'].append('wait-test-controls.js')
                data = json.dumps(manifest).encode()
            custom.writestr(item, data)
        custom.writestr('wait-test-controls.js', TEST_CONTROLS)
    return target


@pytest_asyncio.fixture
async def wait_browser(server_with_extension, upload_page):  # noqa: F811
    setup = server_with_extension
    server = setup['server']
    connection = profile_connection(server)
    tabs = []

    async def raw(action, **data):
        return await connection.send_request_and_wait({
            'id': str(uuid.uuid4()), 'type': 'request', 'action': action, 'data': data
        }, timeout=5)

    async def control(action='state', **data):
        result = await raw(f'test.wait.{action}', **data)
        assert result.get('type') == 'response', result
        return result['data']

    async with Client(f"http://localhost:{setup['mcp_port']}/mcp/") as client:
        async def call(name, **args):
            result = await client.call_tool(name, {'profile_id': connection.profile_id, **args})
            assert not result.is_error, result
            return result.content[0].text

        try:
            for _ in range(2):
                tabs.append(await open_fixture(server, upload_page))
            yield SimpleNamespace(server=server, call=call, control=control, raw=raw,
                                  tab=tabs[0], other=tabs[1])
        finally:
            # Tab closure works even if the regression leaves a script job pending.
            for tab in tabs:
                await raw('tabs.close', tabId=tab)


async def assert_next_script(browser, enabled):
    state = await browser.control('configure', enabled=enabled)
    assert state['enabled'] is enabled and state['transition'] is None, state
    assert state['jobs'] == [] and not state['prompt'], state
    if enabled:
        await browser.control('remember', tabId=browser.other)
    result = await browser.call('content_execute_script', tab_id=browser.other, code='40 + 2')
    assert result.rstrip().endswith('42'), result


@pytest.mark.asyncio
async def test_wait_timeout_releases_job_before_consent_toggle_and_other_tab(wait_browser):
    browser = wait_browser
    script = '''globalThis.waitAttempts = (globalThis.waitAttempts || 0) + 1;
waitAttempts === 1 ? null : new Promise(() => {})'''
    result = await browser.call('content_wait', tab_id=browser.tab, script=script,
                                timeout=.35, interval=.1)
    assert result.startswith('Failed to wait: Timed out after 350 ms:'), result
    state = await browser.control()
    assert state['jobs'] == [], state
    await assert_next_script(browser, enabled=True)


@pytest.mark.asyncio
async def test_deadline_expires_queued_approval_without_injection(wait_browser):
    browser = wait_browser
    await browser.control('configure', enabled=True)
    result = await browser.raw('test.wait.run', tabId=browser.tab, timeoutMs=250,
                               script='globalThis.unapproved = true; 42')
    assert result.get('data', {}).get('code') == 'WAIT_TIMEOUT', result
    state = await browser.control()
    assert state['jobs'] == [] and not state['prompt'], state
    await assert_next_script(browser, enabled=False)
    check = await browser_request(browser.server, 'content.execute_script', {
        'tabId': browser.tab, 'script': 'globalThis.unapproved !== true'
    })
    assert check['result'] is True, check


@pytest.mark.asyncio
@pytest.mark.parametrize('consent', [False, True])
async def test_deadline_finishes_first_pending_execution(wait_browser, consent):
    browser = wait_browser
    await browser.control('configure', enabled=consent)
    if consent:
        await browser.control('remember', tabId=browser.tab)
    result = await browser.raw('test.wait.run', tabId=browser.tab, timeoutMs=250,
                               script='new Promise(() => {})')
    assert result.get('data', {}).get('code') == 'WAIT_TIMEOUT', result
    state = await browser.control()
    assert state['jobs'] == [], state
    await assert_next_script(browser, enabled=not consent)


@pytest.mark.asyncio
async def test_bounded_wait_preserves_scope_values_and_errors(wait_browser):
    browser = wait_browser
    for script, expected in [
        ('var value = 42; value', 42), ('value', 42), ('false', False), ('0', 0),
        ('({error:"data",timedOut:true})', {'error': 'data', 'timedOut': True}),
        ('Promise.resolve({value:null})', {'value': None})
    ]:
        result = await browser.call('content_wait', tab_id=browser.tab, script=script)
        assert result.startswith('Ready after '), result
        assert json.loads(result.split(':\n', 1)[1]) == expected, result
    result = await browser.call('content_wait', tab_id=browser.tab, script="''")
    assert result.startswith('Ready after ') and result.endswith(':\n'), result
    for script in ["throw ''", 'Promise.reject(new Error("expected"))', 'document.body']:
        result = await browser.call('content_wait', tab_id=browser.tab, script=script)
        assert result.startswith('Failed to wait: Wait script failed:'), result
    for script in ['null', 'undefined']:
        result = await browser.call('content_wait', tab_id=browser.tab, script=script,
                                    timeout=.15, interval=.1)
        assert result.startswith('Failed to wait: Timed out after 150 ms:'), result
