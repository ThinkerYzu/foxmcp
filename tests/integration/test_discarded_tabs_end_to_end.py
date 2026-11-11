"""Discarded-tab reads through MCP HTTP, real Firefox and the production helpers."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from threading import Thread
from types import SimpleNamespace
import uuid
import zipfile

from fastmcp import Client
import pytest
import pytest_asyncio

import test_imports  # noqa: F401
from test_config import profile_connection


# This companion runs only in a temporary XPI, after the unchanged background.js.
# Count real reload calls, and hold them until both readers enter the helper.
# Network request counts alone miss duplicate reloads coalesced by Firefox.
TEST_CONTROLS = r"""
(() => {
  const states = new Map();
  const reload = browser.tabs.reload.bind(browser.tabs);
  browser.tabs.reload = async (tabId, ...args) => {
    const state = states.get(tabId);
    if (state) {
      state.reloads++;
      if (state.hold) await state.gate;
    }
    return reload(tabId, ...args);
  };
  const load = loadDiscardedTab;
  loadDiscardedTab = (tab, ...args) => {
    const state = states.get(tab.id);
    if (state) state.entries++;
    return load(tab, ...args);
  };
  const handleTest = handleTestAction;
  handleTestAction = async (id, action, data) => {
    if (!action.startsWith('test.discarded.')) return handleTest(id, action, data);
    try {
      if (action === 'test.discarded.prepare') {
        const state = states.get(data.tabId) || {reloads: 0};
        state.entries = 0;
        state.hold = Boolean(data.hold);
        state.gate = new Promise(resolve => { state.release = resolve; });
        states.set(data.tabId, state);
        await browser.tabs.discard(data.tabId);
      } else if (action === 'test.discarded.release') {
        const state = states.get(data.tabId);
        if (state) { state.hold = false; state.release(); }
      } else if (action !== 'test.discarded.inspect') {
        throw new Error('Unknown discarded-tab test control');
      }
      const state = states.get(data.tabId);
      const active = await browser.tabs.query({active: true, currentWindow: true});
      sendResponse(id, action, {tab: await browser.tabs.get(data.tabId),
        reloads: state?.reloads || 0, entries: state?.entries || 0,
        activeTab: active[0]?.id});
    } catch (error) { sendError(id, 'API_ERROR', error.message); }
  };
})();
"""


@pytest.fixture
def firefox_extension(tmp_path):
    """Add test controls to a copy without changing the release XPI or its cache."""
    root = Path(__file__).resolve().parents[2]
    source = root / 'dist/packages/foxmcp@codemud.org.xpi'
    assert source.exists(), "Run make package before the Firefox tests"
    target = tmp_path / 'discarded-tab-test.xpi'
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, 'w') as custom:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == 'manifest.json':
                manifest = json.loads(data)
                manifest['background']['scripts'].append('discarded-tab-test-controls.js')
                data = json.dumps(manifest).encode()
            custom.writestr(item, data)
        custom.writestr('discarded-tab-test-controls.js', TEST_CONTROLS)
    return target


@pytest.fixture
def discarded_site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'''<!doctype html><title>Discarded fixture</title>
<main id="ready">Loaded discarded tab</main>'''
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    site = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=site.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{site.server_port}/'
    finally:
        site.shutdown()
        site.server_close()
        thread.join(timeout=5)


@pytest_asyncio.fixture
async def discarded_browser(server_with_extension, discarded_site):
    setup = server_with_extension
    server = setup['server']
    connection = profile_connection(server)
    tab_id = None

    async def control(action='inspect', **data):
        response = await connection.send_request_and_wait({
            'id': str(uuid.uuid4()), 'type': 'request',
            'action': f'test.discarded.{action}', 'data': {'tabId': tab_id, **data}
        })
        assert response.get('type') == 'response', response
        return response['data']

    async with Client(f"http://localhost:{setup['mcp_port']}/mcp/") as client:
        async def call(name, **args):
            result = await client.call_tool(name, {'profile_id': connection.profile_id, **args})
            assert not result.is_error, result
            return result.content[0].text

        try:
            created = await call('tabs_create', url=discarded_site, active=False)
            match = re.search(r'ID (\d+)', created)
            assert match, created
            tab_id = int(match[1])
            state = await wait_for_state(
                control, lambda state: state['tab']['status'] == 'complete')
            assert not state['tab']['active'], state
            active_tab = state['activeTab']
            assert active_tab != tab_id, state
            yield SimpleNamespace(call=call, control=control, tab_id=tab_id,
                                  active_tab=active_tab, firefox=setup['firefox'])
        finally:
            if tab_id is not None:
                # Release any held API call before closing a tab or tearing down Firefox.
                await control('release')
                await call('tabs_close', tab_id=tab_id)


async def wait_for_state(control, predicate, timeout=10):
    async def poll():
        while True:
            state = await control()
            if predicate(state):
                return state
            await asyncio.sleep(.05)
    return await asyncio.wait_for(poll(), timeout=timeout)


def assert_loaded(state, browser, reloads):
    assert not state['tab']['discarded'], state
    assert state['tab']['status'] == 'complete', state
    assert not state['tab']['active'], state
    assert state['activeTab'] == browser.active_tab, state
    assert state['reloads'] == reloads, state


@pytest.mark.asyncio
@pytest.mark.parametrize('tool', ['content_get_text', 'content_get_html'])
async def test_read_loads_discarded_tab_without_activation(discarded_browser, tool):
    browser = discarded_browser
    assert not browser.firefox.cache_profiles
    state = await browser.control('prepare')
    assert state['tab']['discarded'] and not state['tab']['active'], state
    result = await browser.call(tool, tab_id=browser.tab_id)
    assert 'Loaded discarded tab' in result, result
    if tool == 'content_get_html':
        assert '<main id="ready">' in result, result
    assert_loaded(await browser.control(), browser, reloads=1)

    # A read of the now-loaded tab must not reload it again.
    assert 'Loaded discarded tab' in await browser.call(tool, tab_id=browser.tab_id)
    assert_loaded(await browser.control(), browser, reloads=1)


@pytest.mark.asyncio
async def test_concurrent_readers_share_reload_and_can_reload_after_rediscard(discarded_browser):
    browser = discarded_browser
    for expected_reloads in (1, 2):
        state = await browser.control('prepare', hold=True)
        assert state['tab']['discarded'] and not state['tab']['active'], state
        reads = [asyncio.create_task(browser.call(tool, tab_id=browser.tab_id))
                 for tool in ('content_get_text', 'content_get_html')]
        try:
            state = await wait_for_state(browser.control, lambda state: state['entries'] == 2,
                                         timeout=5)
            assert state['reloads'] == expected_reloads, state
            await browser.control('release')
            results = await asyncio.gather(*reads)
            assert all('Loaded discarded tab' in result for result in results), results
            assert '<main id="ready">' in results[1], results
            assert_loaded(await browser.control(), browser, expected_reloads)
        finally:
            await browser.control('release')
            await asyncio.gather(*reads, return_exceptions=True)
