"""Frame discovery, targeted scripts and tab-wide consent in real Firefox/MCP HTTP."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
import uuid
import zipfile

from fastmcp import Client
import pytest
import pytest_asyncio

import test_imports  # noqa: F401
from test_config import profile_connection
from test_file_loading import open_fixture


# Test-only controls operate the real gate and inspect its state. Script
# execution and origin validation always use the production implementation.
TEST_CONTROLS = r"""
(() => {
  let held = null;
  const execute = browser.tabs.executeScript.bind(browser.tabs);
  browser.tabs.executeScript = async (tabId, options) => {
    const result = await execute(tabId, options);
    if (held?.tabId === tabId &&
        options.code?.startsWith('this.Object.defineProperty(this, "__foxmcpFrame_')) {
      held.prepared = true;
      await held.promise;
    }
    return result;
  };
  const original = handleTestAction;
  handleTestAction = async (id, action, data) => {
    if (!action.startsWith('test.frames.')) return original(id, action, data);
    try {
      if (action === 'test.frames.hold') {
        held = {tabId: data.tabId, prepared: false};
        held.promise = new Promise(resolve => { held.release = resolve; });
      } else if (action === 'test.frames.release') {
        held?.release();
        held = null;
      } else if (action === 'test.frames.configure') scriptConsent.configure(data.enabled);
      else if (action === 'test.frames.remember') {
        const tab = await browser.tabs.get(data.tabId);
        scriptConsent.decisions.set(tab.id,
          {origin: scriptConsent.origin(tab.url), allowed: data.allowed});
      } else if (action === 'test.frames.decide') {
        const view = await scriptConsent.view();
        if (!view) throw Error('No active consent prompt');
        await scriptConsent.decide(view.token, data.allowed);
        for (const view of browser.extension.getViews({type: 'popup'})) view.close();
      } else if (action !== 'test.frames.state') throw Error('Unknown frame control');
      sendResponse(id, action, {enabled: scriptConsent.enabled,
        prompt: Boolean((await scriptConsent.view())?.visible),
        decisions: scriptConsent.decisions.size,
        jobs: scriptConsent.jobs.size, prepared: Boolean(held?.prepared)});
    } catch (error) { sendError(id, error.code || 'API_ERROR', error.message); }
  };
})();
"""


@pytest.fixture
def firefox_extension(tmp_path, request):
    root = Path(__file__).resolve().parents[2]
    source = root / 'dist/packages/foxmcp@codemud.org.xpi'
    assert source.exists(), 'Run make package first'
    target = tmp_path / 'frame-test.xpi'
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, 'w') as custom:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == 'manifest.json':
                manifest = json.loads(data)
                manifest['background']['scripts'].append('frame-test-controls.js')
                if getattr(request, 'param', None) == 'restricted':
                    manifest['permissions'].remove('<all_urls>')
                    manifest['permissions'].append('http://127.0.0.1/*')
                    for content in manifest['content_scripts']:
                        content['matches'] = ['http://127.0.0.1/*']
                data = json.dumps(manifest).encode()
            custom.writestr(item, data)
        custom.writestr('frame-test-controls.js', TEST_CONTROLS)
    return target


@pytest.fixture
def frame_site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?')[0]
            titles = {'/': 'Top', '/same': 'Same', '/nested': 'Nested',
                      '/cross': 'Cross', '/leaf': 'Leaf'}
            title = titles.get(path, 'Other')
            children = ''
            if path == '/':
                cross_url = f'http://localhost:{self.server.server_port}/cross'
                children = ('<iframe id="same" src="/same"></iframe>'
                            f'<iframe id="cross" src="{cross_url}"></iframe>')
            elif path == '/same':
                children = '<iframe id="nested" src="/nested"></iframe>'
            elif path == '/cross':
                children = '<iframe id="leaf" src="/leaf"></iframe>'
            body = f'<!doctype html><title>{title}</title><input id="upload">{children}'.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
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


DISCOVER = r'''JSON.stringify((() => {
  const frames = [];
  function visit(win, parentId = -1) {
    const id = browser.runtime.getFrameId(win);
    frames.push({frame_id: id, parent_frame_id: parentId});
    for (let i = 0; i < win.frames.length; i++) visit(win.frames[i], id);
  }
  visit(window);
  return frames;
})())'''


@pytest_asyncio.fixture
async def frame_browser(server_with_extension, frame_site):
    setup = server_with_extension
    server = setup['server']
    connection = profile_connection(server)
    tab = await open_fixture(server, frame_site)

    async def raw(action, **data):
        return await connection.send_request_and_wait({
            'id': str(uuid.uuid4()), 'type': 'request', 'action': action, 'data': data}, timeout=10)

    async def control(action='state', **data):
        response = await raw(f'test.frames.{action}', **data)
        assert response.get('type') == 'response', response
        return response['data']

    async with Client(f"http://localhost:{setup['mcp_port']}/mcp/") as client:
        async def call(code, **kwargs):
            result = await client.call_tool('content_execute_script', {
                'profile_id': connection.profile_id, 'tab_id': tab, 'code': code, **kwargs})
            assert not result.is_error, result
            return result.content[0].text

        async def value(code, **kwargs):
            result = await call(f'JSON.stringify({code})', **kwargs)
            assert result.startswith('Script result'), result
            return json.loads(result.split('\n', 1)[1])

        try:
            tree_text = await call(DISCOVER)
            assert tree_text.startswith('Script result'), tree_text
            tree = json.loads(tree_text.split('\n', 1)[1])
            assert len(tree) == 5, tree
            titles = {}
            for frame in tree:
                title = await value('document.title', frame_id=frame['frame_id'])
                titles[title] = frame['frame_id']
            yield SimpleNamespace(tab=tab, call=call, value=value, raw=raw, control=control,
                                  tree=tree, frames=titles, site=frame_site)
        finally:
            await raw('tabs.close', tabId=tab)


@pytest.mark.asyncio
async def test_discovery_and_targeting_include_nested_cross_origin_frames(frame_browser):
    b = frame_browser
    assert set(b.frames) == {'Top', 'Same', 'Nested', 'Cross', 'Leaf'}
    assert b.frames['Top'] == 0
    parents = {f['frame_id']: f['parent_frame_id'] for f in b.tree}
    assert parents[b.frames['Nested']] == b.frames['Same']
    assert parents[b.frames['Leaf']] == b.frames['Cross']
    assert parents[b.frames['Cross']] == 0
    assert await b.value('document.title') == 'Top'
    assert await b.value('document.title', frame_id=0) == 'Top'
    for title, frame_id in b.frames.items():
        assert await b.value('document.title', frame_id=frame_id) == title
        await b.call('globalThis.targeted = true', frame_id=frame_id)
        assert await b.value('globalThis.targeted', frame_id=frame_id) is True
        if frame_id:
            assert await b.value('typeof globalThis.targeted') == 'undefined'
        await b.call('delete globalThis.targeted', frame_id=frame_id)
    assert await b.value('typeof globalThis.targeted') == 'undefined'


@pytest.mark.asyncio
async def test_missing_removed_and_invalid_frames_never_execute_in_top(frame_browser):
    b = frame_browser
    removed = b.frames['Same']
    await b.call('document.querySelector("#same").remove(); true')
    for frame in [removed, b.frames['Nested'], 2147483647]:
        result = await b.call('globalThis.unwanted = true; "wrong frame"', frame_id=frame)
        assert result.startswith('Failed to execute script:'), result
        assert 'frame' in result.lower(), result
    assert await b.value('typeof globalThis.unwanted') == 'undefined'
    for frame in [-1, True, False, 1.5, '2', None]:
        result = await b.raw('content.execute_script', tabId=b.tab,
                             frameId=frame, script='globalThis.unwanted = true')
        assert result.get('data', {}).get('code') == 'INVALID_PARAMETER', result
    assert await b.value('typeof globalThis.unwanted') == 'undefined'


@pytest.mark.asyncio
async def test_tab_approval_includes_all_frames_and_cross_origin_navigation(frame_browser):
    b = frame_browser
    await b.control('configure', enabled=True)
    # First injection targets a child, but the displayed approval belongs to its tab.
    task = asyncio.create_task(b.call('JSON.stringify(document.title)', frame_id=b.frames['Cross']))
    for _ in range(100):
        if (await b.control())['prompt']:
            break
        await asyncio.sleep(.05)
    else:
        pytest.fail('Child injection never requested tab approval')
    await b.control('decide', allowed=True)
    result = await task
    assert result.endswith('"Cross"'), result
    for title, frame_id in b.frames.items():
        assert await b.value('document.title', frame_id=frame_id) == title
    assert (await b.control()) == {
        'enabled': True, 'prompt': False, 'decisions': 1, 'jobs': 0, 'prepared': False}
    for title in ['Nested', 'Cross', 'Leaf']:
        frame_id = b.frames[title]
        # The gated child path preserves promise results, global declarations,
        # strict scripts and script errors in the frame's isolated scope.
        assert (await b.call('Promise.resolve(42)', frame_id=frame_id)).endswith('42')
        declaration = ('var frameNumber = 40; '
                       'function frameAnswer() { return frameNumber + 2; }; frameAnswer()')
        assert (await b.call(declaration, frame_id=frame_id)).endswith('42')
        assert (await b.call('frameAnswer()', frame_id=frame_id)).endswith('42')
        assert (await b.call('"use strict"; document.title', frame_id=frame_id)).endswith(title)
        assert 'frame-specific failure' in await b.call(
            'throw new Error("frame-specific failure")', frame_id=frame_id)
    # Child origin changes are covered by the same tab decision.
    new_url = b.site + 'other'
    await b.call(f'document.querySelector("#cross").src = {json.dumps(new_url)}; true')
    for _ in range(100):
        try:
            title = await b.value('document.title', frame_id=b.frames['Cross'])
            if title == 'Other':
                break
        except AssertionError:
            pass
        await asyncio.sleep(.05)
    else:
        pytest.fail('Child frame navigation did not finish')
    assert (await b.control())['decisions'] == 1
    assert not (await b.control())['prompt']


@pytest.mark.asyncio
async def test_tab_denial_applies_to_cross_origin_and_nested_frames(frame_browser):
    b = frame_browser
    await b.control('configure', enabled=True)
    await b.control('remember', tabId=b.tab, allowed=False)
    for frame_id in b.frames.values():
        result = await b.call('globalThis.unwanted = true', frame_id=frame_id)
        assert 'denied' in result.lower(), result
    await b.control('configure', enabled=False)
    for frame_id in b.frames.values():
        assert await b.value('typeof globalThis.unwanted', frame_id=frame_id) == 'undefined'


@pytest.mark.asyncio
async def test_top_origin_navigation_invalidates_frame_approval(frame_browser):
    b = frame_browser
    await b.control('configure', enabled=True)
    await b.control('remember', tabId=b.tab, allowed=True)
    assert await b.value('document.title', frame_id=b.frames['Leaf']) == 'Leaf'
    response = await b.raw('navigation.go_to_url', tabId=b.tab,
                           url=b.site.replace('127.0.0.1', 'localhost'))
    assert response.get('type') == 'response', response
    for _ in range(100):
        if (await b.control())['decisions'] == 0:
            break
        await asyncio.sleep(.05)
    assert (await b.control())['decisions'] == 0
    await b.control('configure', enabled=False)


@pytest.mark.asyncio
@pytest.mark.parametrize('firefox_extension', ['restricted'], indirect=True)
async def test_missing_child_host_permission_reports_error_without_fallback(
    server_with_extension, frame_site
):
    setup = server_with_extension
    server = setup['server']
    connection = profile_connection(server)
    tab = await open_fixture(server, frame_site)
    async with Client(f"http://localhost:{setup['mcp_port']}/mcp/") as client:
        async def call(code, **args):
            result = await client.call_tool('content_execute_script', {
                'profile_id': connection.profile_id, 'tab_id': tab, 'code': code, **args})
            assert not result.is_error, result
            return result.content[0].text
        try:
            found = await call('browser.runtime.getFrameId(document.querySelector("#cross"))')
            frame_id = int(found.split('\n', 1)[1])
            assert frame_id > 0
            result = await call('globalThis.unwanted = true', frame_id=frame_id)
            assert result.startswith('Failed to execute script:'), result
            assert 'permission' in result.lower() or 'inaccessible' in result.lower(), result
            assert (await call('typeof globalThis.unwanted')).endswith('undefined')
        finally:
            await connection.send_request_and_wait({
                'id': str(uuid.uuid4()), 'type': 'request', 'action': 'tabs.close',
                'data': {'tabId': tab}})


@pytest.mark.asyncio
async def test_gated_frame_lexical_scope_matches_ordinary_injection(frame_browser):
    b = frame_browser
    frame = b.frames['Cross']
    ordinary_code = 'let ordinaryLet = 40; const ordinaryConst = 2; ordinaryLet + ordinaryConst'
    assert (await b.call(ordinary_code, frame_id=frame)).endswith('42')
    ordinary = await b.value('[typeof ordinaryLet, typeof ordinaryConst]', frame_id=frame)
    await b.control('configure', enabled=True)
    await b.control('remember', tabId=b.tab, allowed=True)
    approved_code = 'let approvedLet = 40; const approvedConst = 2; approvedLet + approvedConst'
    assert (await b.call(approved_code, frame_id=frame)).endswith('42')
    approved = await b.value('[typeof approvedLet, typeof approvedConst]', frame_id=frame)
    assert approved == ordinary, (ordinary, approved)
    assert await b.value(
        'Object.getOwnPropertyNames(globalThis).filter(key => key.startsWith("__foxmcpFrame_"))',
        frame_id=frame) == []
    # Guard prefixes must not introduce TDZ failures for caller declarations.
    assert (await b.call('const Object = 7; const globalThis = 8; Object + globalThis',
                         frame_id=frame)).endswith('15')
    assert (await b.call('Object + globalThis', frame_id=frame)).endswith('15')


@pytest.mark.asyncio
@pytest.mark.parametrize('navigation', ['child', 'top'])
async def test_navigation_during_frame_preparation_cannot_run_caller_in_replacement(
    frame_browser, navigation
):
    b = frame_browser
    await b.control('configure', enabled=True)
    await b.control('remember', tabId=b.tab, allowed=True)
    await b.control('hold', tabId=b.tab)
    pending = asyncio.create_task(b.call('globalThis.unwanted = true', frame_id=b.frames['Cross']))
    try:
        for _ in range(100):
            if (await b.control())['prepared']:
                break
            await asyncio.sleep(.05)
        else:
            pytest.fail('Frame preparation did not reach the test barrier')
        if navigation == 'child':
            destination = json.dumps(b.site + 'other')
            await b.call(f'document.querySelector("#cross").src = {destination}; true')
            for _ in range(100):
                title = await b.value(
                    'document.querySelector("#cross").contentDocument?.title ?? null')
                if title == 'Other':
                    break
                await asyncio.sleep(.05)
            else:
                pytest.fail('Replacement child never loaded')
        else:
            response = await b.raw('navigation.go_to_url', tabId=b.tab,
                                   url=b.site.replace('127.0.0.1', 'localhost'))
            assert response.get('type') == 'response', response
            for _ in range(100):
                if (await b.control())['decisions'] == 0:
                    break
                await asyncio.sleep(.05)
        await b.control('release')
        result = await pending
        assert result.startswith('Failed to execute script:'), result
        assert 'changed' in result.lower(), result
        await b.control('configure', enabled=False)
        assert await b.value('typeof globalThis.unwanted') == 'undefined'
        if navigation == 'child':
            actual = await b.value('typeof globalThis.unwanted', frame_id=b.frames['Cross'])
            assert actual == 'undefined'
    finally:
        await b.control('release')
        if not pending.done():
            await pending
