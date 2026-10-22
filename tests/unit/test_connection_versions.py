"""Advisory version diagnostics must not gate requests or leak across sockets."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock

import pytest

from server.server import FoxMCPServer
from server.version import VERSION


@pytest.fixture
def server():
    instance = FoxMCPServer(start_mcp=False)
    instance.VERSION_REPORT_TIMEOUT = 0.01
    return instance


@pytest.mark.asyncio
@pytest.mark.parametrize('version', [VERSION, '0.0.1'])
async def test_reports_versions_without_blocking_tools(server, caplog, version):
    with caplog.at_level(logging.INFO):
        await server.handle_extension_message(json.dumps({'type': 'hello', 'data': {'version': version}}))
    assert server.extension_version == version
    assert ('version mismatch' in caplog.text) == (version != VERSION)
    assert f'extension {version}, server {VERSION}' in caplog.text
    pending = asyncio.get_running_loop().create_future()
    server.pending_requests['tool'] = pending
    await server.handle_extension_message(json.dumps({'id': 'tool', 'type': 'response', 'data': {'tabs': []}}))
    assert (await pending)['data'] == {'tabs': []}


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [None, [], {}, {'version': None}, {'version': 123},
                                   {'version': 'bad\nversion'}, {'version': VERSION + '\n'}, {'version': '1.' + '0' * 70}])
async def test_malformed_versions_remain_unknown(server, payload):
    await server.handle_extension_message(json.dumps({'type': 'hello', 'data': payload}))
    assert server.extension_version is None


class Peer:
    remote_address = ('127.0.0.1', 12345)
    close_code = None

    def __init__(self):
        self.send = AsyncMock()
        self.messages = asyncio.Queue()

    def __aiter__(self):
        return self

    async def __anext__(self):
        message = await self.messages.get()
        if message is None:
            raise StopAsyncIteration
        return message

    async def close(self):
        self.close_code = 1000
        await self.messages.put(None)


@pytest.mark.asyncio
async def test_legacy_peer_gets_warning_but_can_ping(server, caplog):
    peer = Peer()
    task = asyncio.create_task(server.handle_extension_connection(peer))
    try:
        await asyncio.sleep(0.03)
        assert json.loads(peer.send.call_args_list[0].args[0]) == {'type': 'hello', 'data': {'version': VERSION}}
        assert 'Extension version unavailable' in caplog.text
        await peer.messages.put(json.dumps({'type': 'request', 'action': 'ping', 'id': 'legacy'}))
        await asyncio.sleep(0.01)
        assert json.loads(peer.send.call_args.args[0])['id'] == 'legacy'
    finally:
        await peer.close()
        await task
    assert server.extension_version is None


@pytest.mark.asyncio
async def test_replacement_resets_version_and_old_handler_cannot_clear_new_state(server, caplog):
    old, new = Peer(), Peer()
    first = asyncio.create_task(server.handle_extension_connection(old))
    second = None
    try:
        await asyncio.sleep(0)
        await old.messages.put(json.dumps({'type': 'hello', 'data': {'version': '0.0.1'}}))
        await asyncio.sleep(0)
        assert server.extension_version == '0.0.1'
        second = asyncio.create_task(server.handle_extension_connection(new))
        await asyncio.sleep(0)
        assert server.extension_version is None
        await new.messages.put(json.dumps({'type': 'hello', 'data': {'version': VERSION}}))
        await asyncio.sleep(0.03)
        assert server.extension_connection is new
        assert server.extension_version == VERSION
        assert 'Extension version unavailable' not in caplog.text
    finally:
        await old.close()
        await new.close()
        await first
        if second:
            await second
    caplog.clear()
    await asyncio.sleep(0.03)
    assert 'Extension version unavailable' not in caplog.text
