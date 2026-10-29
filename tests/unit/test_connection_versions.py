"""Advisory version diagnostics must not gate requests or leak across sockets."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock

import pytest

from server.server import FoxMCPServer
from server.browser_profile import BrowserProfile
from server.version import VERSION


@pytest.fixture
def server():
    instance = BrowserProfile(FoxMCPServer(start_mcp=False), AsyncMock(), "test-profile", "moz-extension://test")
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
