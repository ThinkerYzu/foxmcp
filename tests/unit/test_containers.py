"""Container contracts, selection safety and tool registration."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from server.mcp_tools import FoxMCPTools
from server.browser_proxy import PROTOCOL_VERSION


@pytest.fixture
def server():
    return type("Browser", (), {"send_request_and_wait": AsyncMock(
        return_value={"type": "response", "data": {}})})()


@pytest.fixture
def call(server):
    tools = FoxMCPTools(server)

    async def invoke(tool_name, **args):
        return await (await tools.mcp.get_tool(tool_name)).fn(profile_id="test-profile", **args)
    return invoke


@pytest.mark.asyncio
@pytest.mark.parametrize("name,args,action,data", [
    ("containers_list", {}, "containers.list", {}),
    ("tabs_create", {"url": "https://example.org"}, "tabs.create",
     {"url": "https://example.org", "active": True, "pinned": False}),
    ("tabs_create", {"url": "https://example.org", "cookie_store_id": "opaque-store"},
     "tabs.create_in_store", {"url": "https://example.org", "active": True,
                              "pinned": False, "cookieStoreId": "opaque-store"}),
    ("tabs_list", {"window_id": "8", "cookie_store_id": "opaque-store"}, "tabs.list",
     {"windowId": 8, "cookieStoreId": "opaque-store"}),
])
async def test_requests(call, server, name, args, action, data):
    await call(name, **args)
    request = server.send_request_and_wait.call_args.args[0]
    assert request["action"] == action
    assert request["data"] == data


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["", "   ", 2, True, [], {}])
@pytest.mark.parametrize("name", ["tabs_list", "tabs_create"])
async def test_rejects_invalid_store_before_sending(call, server, value, name):
    args = {"cookie_store_id": value}
    if name == "tabs_create":
        args["url"] = "https://example.org"
    assert "INVALID_PARAMETER" in await call(name, **args)
    server.send_request_and_wait.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("actual", [None, "firefox-default", "another-store"])
async def test_no_success_or_retry_on_wrong_store(call, server, actual):
    server.send_request_and_wait.return_value = {"type": "response", "data": {
        "tab": {"id": 17, **({"cookieStoreId": actual} if actual else {})}}}
    result = await call("tabs_create", url="https://example.org", cookie_store_id="wanted")
    assert "Error: API_ERROR" in result and "ID 17" in result
    server.send_request_and_wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_old_extension_rejection_never_replays(call, server):
    server.send_request_and_wait.return_value = {"type": "error", "data": {
        "code": "UNKNOWN_ACTION", "message": "Unknown tab action"}}
    result = await call("tabs_create", url="https://example.org", cookie_store_id="wanted")
    assert "Update the extension" in result
    server.send_request_and_wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_listing_retains_ids_and_never_assumes_default(call, server):
    server.send_request_and_wait.return_value = {"type": "response", "data": {
        "tabs": [{"id": 7, "windowId": 1, "index": 2}]}}
    result = await call("tabs_list")
    assert "ID 7:" in result
    assert "[window 1, index 2] [cookie store unavailable]" in result
    assert "Cannot verify" in await call("tabs_list", cookie_store_id="firefox-default")


@pytest.mark.asyncio
async def test_disabled_discovery_does_not_disable_tab_selection(server):
    tools = FoxMCPTools(server, disabled_groups=["containers"])
    names = {tool.name for tool in await tools.mcp.list_tools()}
    assert "containers_list" not in names and "tabs_create" in names
    tools = FoxMCPTools(server, disabled_groups=["containers"], enabled_tools=["containers_list"])
    assert "containers_list" in {tool.name for tool in await tools.mcp.list_tools()}


def test_permissions_and_protocol_bump():
    manifest = json.loads((Path(__file__).resolve().parents[2] / "extension/manifest.json").read_text())
    assert {"cookies", "contextualIdentities"} <= set(manifest["permissions"])
    assert PROTOCOL_VERSION == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('name,args,action,data', [
    ('containers_create', {'name':'Work'}, 'containers.create',
     {'name':'Work', 'color':'blue', 'icon':'fingerprint'}),
    ('containers_update', {'cookie_store_id':'opaque', 'name':'New'}, 'containers.update',
     {'cookieStoreId':'opaque', 'name':'New'}),
    ('containers_remove', {'cookie_store_id':'opaque'}, 'containers.remove', {'cookieStoreId':'opaque'}),
])
async def test_lifecycle_requests(call, server, name, args, action, data):
    await call(name, **args)
    request = server.send_request_and_wait.call_args.args[0]
    assert request['action'] == action and request['data'] == data


@pytest.mark.asyncio
@pytest.mark.parametrize('name,args', [
    ('containers_create', {'name':''}),
    ('containers_create', {'name':False}),
    ('containers_update', {'cookie_store_id':'opaque'}),
    ('containers_update', {'cookie_store_id':'firefox-default', 'name':'No'}),
    ('containers_update', {'cookie_store_id':'opaque', 'color':''}),
    ('containers_remove', {'cookie_store_id':'firefox-private'}),
    ('containers_remove', {'cookie_store_id':'firefox-default'}),
    ('containers_remove', {'cookie_store_id':42}),
])
async def test_lifecycle_invalid_input_never_sends(call, server, name, args):
    assert 'INVALID_PARAMETER' in await call(name, **args)
    server.send_request_and_wait.assert_not_called()


@pytest.mark.asyncio
async def test_in_use_error_retains_tab_ids(call, server):
    server.send_request_and_wait.return_value = {'type':'error', 'data': {
        'code':'CONTAINER_IN_USE', 'message':'Close tabs first', 'details':{'tab_ids':[71,72]}}}
    result = await call('containers_remove', cookie_store_id='opaque')
    assert 'CONTAINER_IN_USE' in result and '[71, 72]' in result


@pytest.mark.asyncio
@pytest.mark.parametrize('local_id,remote_id', [(1,2),(2,1)])
async def test_old_and_new_forwarders_reject_each_other(monkeypatch, local_id, remote_id):
    import httpx
    from unittest.mock import Mock
    from server import single_instance
    monkeypatch.setattr(single_instance, 'PROTOCOL_VERSION', local_id)
    client = AsyncMock()
    client.get.return_value = httpx.Response(200, json={
        'server':'FoxMCP', 'protocol_version':remote_id, 'proxy_path':'/proxy'})
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(single_instance.httpx, 'AsyncClient', Mock(return_value=context))
    with pytest.raises(single_instance.IncompatibleServer):
        await single_instance.probe('localhost', 8765)
