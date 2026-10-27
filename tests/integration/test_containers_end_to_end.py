"""Container isolation through MCP and defensive handlers in real Firefox."""
import asyncio
import json
import re
import sqlite3
import shutil
import tempfile
from contextlib import closing
import uuid
from pathlib import Path

import pytest
from fastmcp import Client

from test_file_loading import browser_request, open_fixture, upload_page  # noqa: F401
from test_single_instance import shared  # noqa: F401


def text(result):
    assert not result.is_error, result
    return '\n'.join(block.text for block in result.content if block.type == 'text')


async def call(client, tool_name, **args):
    return text(await client.call_tool(tool_name, args))


async def wait_ready(server, tab_id):
    for _ in range(100):
        data = await browser_request(server, 'content.execute_script', {
            'tabId': tab_id, 'script': "document.readyState === 'complete' && !!document.querySelector('#upload')"
        }, allow_loading=True)
        if data.get('result'):
            return
        await asyncio.sleep(.1)
    pytest.fail('Container fixture did not load')


@pytest.mark.asyncio
async def test_http_container_selection_and_storage_isolation(server_with_extension, upload_page):
    setup = server_with_extension
    server = setup['server']
    tabs = []
    async with Client(f"http://localhost:{setup['mcp_port']}/mcp") as client:
        discovery = json.loads(await call(client, 'containers_list'))
        stores = [item['cookie_store_id'] for item in discovery['containers'][:2]]
        assert len(stores) == 2 and len(set(stores)) == 2, discovery
        stores.append(discovery['default_cookie_store_id'])
        try:
            for index, store in enumerate(stores):
                created = await call(client, 'tabs_create', url=upload_page,
                                     cookie_store_id=store, active=False)
                assert f'[cookie store {store}]' in created, created
                tab_id = int(re.search(r'ID (\d+)', created)[1])
                tabs.append(tab_id)
                await wait_ready(server, tab_id)
                result = await browser_request(server, 'content.execute_script', {
                    'tabId': tab_id, 'script': f'''document.cookie = 'foxmcp=store{index}; path=/';
                      localStorage.setItem('foxmcp', 'store{index}'); true'''
                })
                assert result['result'] is True
                listing = await call(client, 'tabs_list', cookie_store_id=store)
                assert f'ID {tab_id}:' in listing and f'[cookie store {store}]' in listing
            for index, tab_id in enumerate(tabs):
                data = await browser_request(server, 'content.execute_script', {
                    'tabId': tab_id, 'script': "({cookie: document.cookie, local: localStorage.getItem('foxmcp')})"
                })
                assert data['result'] == {'cookie': f'foxmcp=store{index}', 'local': f'store{index}'}
            window = (await browser_request(server, 'tabs.list', {}))['tabs']
            window_id = next(tab['windowId'] for tab in window if tab['id'] == tabs[0])
            filtered = await call(client, 'tabs_list', window_id=window_id, cookie_store_id=stores[0])
            assert f'ID {tabs[0]}:' in filtered
            assert all(f'ID {tab_id}:' not in filtered for tab_id in tabs[1:])
            before = {tab['id'] for tab in (await browser_request(server, 'tabs.list', {}))['tabs']}
            for store in ('deleted-opaque-id', 'firefox-private'):
                rejected = await call(client, 'tabs_create', url=upload_page, cookie_store_id=store)
                assert 'Error' in rejected, rejected
            after = {tab['id'] for tab in (await browser_request(server, 'tabs.list', {}))['tabs']}
            assert after == before, 'Invalid explicit selection must not open a fallback tab'
        finally:
            for tab_id in tabs:
                await call(client, 'tabs_close', tab_id=tab_id)


@pytest.mark.asyncio
async def test_container_handler_failures_without_mutation(server_with_extension, upload_page):
    server = server_with_extension['server']
    tab_id = await open_fixture(server, upload_page)
    root = Path(__file__).resolve().parents[2]
    background = (root / 'extension/config.js').read_text() + '\n' + (root / 'extension/background.js').read_text()
    checks = r'''
      const checks = [];
      function check(ok, label) { if (!ok) throw Error(label); checks.push(label); }
      const replies = [];
      isConnected = true;
      websocket = {send: raw => replies.push(JSON.parse(raw))};
      let created = 0;
      browser.tabs = {create: async options => {created++; return {id:42, cookieStoreId:'wrong'};},
                      query: async () => []};
      browser.windows = {get: async () => ({id:7, incognito:true}),
                         getLastFocused: async () => ({id:7, incognito:false})};
      async function expect(action, data, code) {
        await handleMessage({id:'case', type:'request', action, data});
        check(replies.at(-1).data.code === code, action + ' ' + code);
      }
      await expect('containers.list', {}, 'UNSUPPORTED_API');
      browser.contextualIdentities = {query: async () => {throw Error('Contextual identities are currently disabled');}};
      await expect('containers.list', {}, 'CONTAINERS_UNAVAILABLE');
      browser.contextualIdentities.query = async () => {throw Error('unexpected failure');};
      await expect('containers.list', {}, 'API_ERROR');
      browser.contextualIdentities.query = async () => [{cookieStoreId:'opaque'}];
      await expect('tabs.create_in_store', {cookieStoreId:'deleted'}, 'CONTAINER_NOT_FOUND');
      await expect('tabs.create_in_store', {cookieStoreId:3}, 'INVALID_PARAMETER');
      await expect('tabs.create_in_store', {cookieStoreId:'firefox-private'}, 'INVALID_PARAMETER');
      await expect('tabs.create_in_store', {cookieStoreId:'opaque', windowId:7}, 'INVALID_PARAMETER');
      check(created === 0, 'validation before creation');
      await expect('tabs.create_in_store', {cookieStoreId:'opaque'}, 'API_ERROR');
      check(created === 1 && replies.at(-1).data.details.tab_id === 42, 'mismatch identifies created tab without retry');
      return checks;
    '''
    # Execute the complete product file with a controlled browser API. The real
    # extension, its preferences and its connection are unaffected by these mocks.
    script = '''(async () => {
      const event = {addListener(){}};
      const browser = {runtime:{getManifest:()=>({version:'1.4.0'}),onMessage:event},
        menus:{create(){},onShown:event,onClicked:event},
        storage:{onChanged:event,sync:{get:()=>new Promise(()=>{})}}};
      const quiet = {log(){},error(){},warn(){},trace(){}};
      const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
      return await new AsyncFunction('browser','window','console', SOURCE + '\\n' + CHECKS)(browser,{},quiet);
    })()'''.replace('SOURCE', json.dumps(background)).replace('CHECKS', json.dumps(checks))
    try:
        data = await browser_request(server, 'content.execute_script', {'tabId': tab_id, 'script': script})
        assert len(data['result']) >= 9, data
    finally:
        await browser_request(server, 'tabs.close', {'tabId': tab_id})


@pytest.mark.asyncio
async def test_container_lifecycle_and_in_use_protection(server_with_extension, upload_page, tmp_path):
    server = server_with_extension['server']
    tools = server.mcp_tools.mcp

    async def tool(tool_name, **args):
        return await (await tools.get_tool(tool_name)).fn(**args)

    identities, tabs = [], []
    try:
        for _ in range(2):
            created = json.loads(await tool('containers_create', name='Duplicate label'))['container']
            identities.append(created['cookie_store_id'])
        assert identities[0] != identities[1]
        store = identities[0]
        updated = json.loads(await tool('containers_update', cookie_store_id=store, name='Renamed', color='red'))['container']
        assert updated == {'cookie_store_id':store, 'name':'Renamed', 'color':'red', 'icon':'fingerprint'}
        invalid = await tool('containers_update', cookie_store_id=store, name='Must not change', icon='not-an-icon')
        assert 'INVALID_PARAMETER' in invalid
        listing = json.loads(await tool('containers_list'))['containers']
        assert next(item for item in listing if item['cookie_store_id'] == store)['name'] == 'Renamed'
        created = await tool('tabs_create', url=upload_page, cookie_store_id=store)
        tab_id = int(re.search(r'ID (\d+)', created)[1])
        tabs.append(tab_id)
        await wait_ready(server, tab_id)
        cookie_name = 'foxmcp_removed_' + uuid.uuid4().hex
        await browser_request(server, 'content.execute_script', {
            'tabId':tab_id, 'script':f"document.cookie='{cookie_name}=yes; path=/; max-age=3600'; localStorage.setItem('removed','yes'); true"})
        # Inspect only this isolated test profile, without interpreting store IDs.
        cookie_db = Path(server_with_extension['firefox'].profile_dir) / 'cookies.sqlite'

        async def cookie_count(expected):
            count = None
            for _ in range(200):
                # Firefox holds an exclusive SQLite lock. Read a disposable
                # database/WAL snapshot, never open or modify the live database.
                with tempfile.TemporaryDirectory(dir=tmp_path) as directory:
                    snapshot = Path(directory) / 'cookies.sqlite'
                    shutil.copyfile(cookie_db, snapshot)
                    wal = cookie_db.with_name('cookies.sqlite-wal')
                    if wal.exists():
                        shutil.copyfile(wal, snapshot.with_name('cookies.sqlite-wal'))
                    try:
                        with closing(sqlite3.connect(snapshot)) as connection:
                            count = connection.execute('SELECT COUNT(*) FROM moz_cookies WHERE name = ?',
                                                       (cookie_name,)).fetchone()[0]
                    except sqlite3.DatabaseError:
                        # A concurrent checkpoint can make a copied snapshot
                        # inconsistent. Retry a fresh copy within the bound.
                        count = None
                if count == expected:
                    return
                await asyncio.sleep(.05)
            pytest.fail(f'Cookie count {count}, expected {expected} after container operation')

        await cookie_count(1)
        rejected = await tool('containers_remove', cookie_store_id=store)
        assert 'CONTAINER_IN_USE' in rejected and str(tab_id) in rejected
        assert any(item['cookie_store_id'] == store for item in json.loads(await tool('containers_list'))['containers'])
        await tool('tabs_close', tab_id=tab_id)
        tabs.remove(tab_id)
        assert json.loads(await tool('containers_remove', cookie_store_id=store)) == {
            'removed':True, 'cookie_store_id':store}
        identities.remove(store)
        await cookie_count(0)
        assert 'CONTAINER_NOT_FOUND' in await tool('containers_remove', cookie_store_id=store)
        assert 'CONTAINER_NOT_FOUND' in await tool('tabs_create', url=upload_page, cookie_store_id=store)
        assert 'INVALID_PARAMETER' in await tool('containers_remove', cookie_store_id='firefox-default')
        assert 'INVALID_PARAMETER' in await tool('containers_remove', cookie_store_id='firefox-private')
    finally:
        for tab_id in tabs:
            await tool('tabs_close', tab_id=tab_id)
        for store in identities:
            await tool('containers_remove', cookie_store_id=store)


@pytest.mark.asyncio
async def test_shared_stdio_containers_survive_disconnect_and_worker_restart(shared, upload_page):
    from firefox_test_utils import FirefoxTestManager, resolve_firefox_path
    from test_single_instance import wait_until_stopped

    start, port = shared
    first = await start()
    await first.initialize()
    second = await start()
    await second.initialize()
    firefox = FirefoxTestManager(firefox_path=resolve_firefox_path(), test_port=port)
    stores, tabs = [], []
    current = second

    async def connected(client):
        for _ in range(150):
            if (await client.call_tool('debug_websocket_status')).startswith('Browser extension connected'):
                return
            await asyncio.sleep(.1)
        pytest.fail('Firefox did not reconnect to shared worker')

    async def value(client, tab_id, expression):
        result = await client.call_tool('content_execute_script', {
            'tab_id':tab_id, 'code':f'JSON.stringify({expression})'})
        assert result.startswith('Script result'), result
        return json.loads(result.partition('\n')[2])

    async def ready(client, tab_id):
        for _ in range(100):
            result = await client.call_tool('content_execute_script', {'tab_id':tab_id,
                'code':"JSON.stringify(document.readyState === 'complete' && !!document.querySelector('#upload'))"})
            if result.partition('\n')[2].strip() == 'true':
                return
            await asyncio.sleep(.1)
        pytest.fail('Shared-stdio container tab did not load')

    try:
        assert firefox.setup_and_start_firefox(headless=True, skip_on_failure=False)
        await connected(first)
        for client in (first, second):
            assert len(await client.list_tool_names()) == 45
            created = json.loads(await client.call_tool('containers_create', {'name':'Persistent test'}))
            stores.append(created['container']['cookie_store_id'])
        for index, client in enumerate((first, second)):
            result = await client.call_tool('tabs_create', {'url':upload_page, 'cookie_store_id':stores[index]})
            tab_id = int(re.search(r'ID (\d+)', result)[1])
            tabs.append(tab_id)
            await ready(client, tab_id)
            await value(client, tab_id, f"(localStorage.setItem('shared','client{index}'), true)")
        assert await value(first, tabs[0], "localStorage.getItem('shared')") == 'client0'
        assert await value(second, tabs[1], "localStorage.getItem('shared')") == 'client1'
        # Different clients selecting the same store share that profile resource.
        result = await second.call_tool('tabs_create', {'url':upload_page, 'cookie_store_id':stores[0]})
        same_tab = int(re.search(r'ID (\d+)', result)[1])
        tabs.append(same_tab)
        await ready(second, same_tab)
        assert await value(second, same_tab, "localStorage.getItem('shared')") == 'client0'
        assert await first.close() == 0
        assert await value(second, tabs[0], "localStorage.getItem('shared')") == 'client0'
        assert await second.close() == 0
        await wait_until_stopped(port)
        current = await start()
        await current.initialize()
        await connected(current)
        discovered = json.loads(await current.call_tool('containers_list'))['containers']
        assert set(stores) <= {item['cookie_store_id'] for item in discovered}
        assert await value(current, tabs[0], "localStorage.getItem('shared')") == 'client0'
        assert await value(current, tabs[1], "localStorage.getItem('shared')") == 'client1'
    finally:
        if current.process.returncode is None:
            for tab_id in tabs:
                await current.call_tool('tabs_close', {'tab_id':tab_id})
            for store in stores:
                await current.call_tool('containers_remove', {'cookie_store_id':store})
        firefox.cleanup()
