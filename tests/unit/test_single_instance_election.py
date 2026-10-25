"""Discovery compatibility and retries after a lost bind or an owner shutdown."""

import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

import test_imports
from server import single_instance
from server.browser_proxy import SERVER_NAME, PROTOCOL_VERSION


@pytest.mark.asyncio
async def test_discovery_retries_after_losing_a_bind(tmp_path, monkeypatch):
    server = Mock(host="localhost", port=8765)
    metadata = {"server": SERVER_NAME, "protocol_version": PROTOCOL_VERSION,
                "proxy_path": "/proxy", "pid": 123}
    monkeypatch.setattr(single_instance, "runtime_directory", lambda: tmp_path)
    monkeypatch.setattr(single_instance, "probe", AsyncMock(side_effect=[None, None, metadata]))
    loser = Mock()
    loser.poll.return_value = 0
    winner = Mock()
    winner.poll.return_value = None
    spawn = Mock(side_effect=[loser, winner])
    monkeypatch.setattr(single_instance, "spawn_worker", spawn)
    websocket = AsyncMock()
    websocket.recv.return_value = json.dumps({"type": "hello", **metadata})
    monkeypatch.setattr(single_instance.websockets, "connect", AsyncMock(return_value=websocket))
    assert await single_instance.discover(server, 60) is websocket
    assert spawn.call_count == 2


@pytest.mark.parametrize("metadata", [
    {}, {"server": "other"},
    {"server": SERVER_NAME, "protocol_version": 999, "proxy_path": "/proxy"},
    {"server": SERVER_NAME, "protocol_version": PROTOCOL_VERSION,
     "proxy_path": "ws://example.org/proxy"},
])
@pytest.mark.asyncio
async def test_occupied_incompatible_port_is_not_replaced(metadata, monkeypatch):
    response = httpx.Response(200, json=metadata)
    client = AsyncMock()
    client.get.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(single_instance.httpx, "AsyncClient", Mock(return_value=context))
    with pytest.raises(single_instance.IncompatibleServer):
        await single_instance.probe("localhost", 8765)


@pytest.mark.asyncio
async def test_timeout_does_not_replay_browser_commands(monkeypatch):
    from server.browser_proxy import RemoteBrowser
    websocket = AsyncMock()
    websocket.__aiter__.return_value = []
    browser = RemoteBrowser(websocket, Mock())
    await browser.reader
    response = await browser.send_request_and_wait({"id": "id", "action": "tabs.create"})
    assert "disconnected" in response["error"]
    websocket.send.assert_not_called()
