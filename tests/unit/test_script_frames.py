"""Raw script frame selection, strict MCP inputs and error propagation."""

from unittest.mock import AsyncMock

from fastmcp import Client
import pytest

import test_imports  # noqa: F401
from server.mcp_tools import FoxMCPTools


@pytest.fixture
def browser():
    return type('Browser', (), {'send_request_and_wait': AsyncMock(return_value={
        'type': 'response', 'data': {'result': 'child', 'url': 'https://example.org/'}})})()


@pytest.mark.asyncio
@pytest.mark.parametrize('selector', [{}, {'frame_id': 0}, {'frame_id': 42}])
async def test_frame_selection_preserves_default_and_profile(browser, selector):
    tools = FoxMCPTools(browser)
    async with Client(tools.mcp) as client:
        result = await client.call_tool('content_execute_script', {
            'profile_id': 7, 'tab_id': 123, 'code': 'document.title', **selector})
    assert 'child' in result.content[0].text
    request = browser.send_request_and_wait.call_args.args[0]
    assert request['profile_id'] == 7
    assert request['action'] == 'content.execute_script'
    assert request['data'] == {'tabId': 123, 'script': 'document.title',
                               **({'frameId': 42} if selector.get('frame_id') else {})}
    assert browser.send_request_and_wait.call_args.kwargs['timeout'] == 300


INVALID_FRAMES = [-1, True, False, '2', 2.5, None, [], {}]


@pytest.mark.asyncio
@pytest.mark.parametrize('frame_id', INVALID_FRAMES)
async def test_mcp_rejects_invalid_frame_before_browser_io(browser, frame_id):
    tools = FoxMCPTools(browser)
    async with Client(tools.mcp) as client:
        with pytest.raises(Exception, match='validation|Validation'):
            await client.call_tool('content_execute_script', {
                'profile_id': 1, 'tab_id': 123, 'code': '42', 'frame_id': frame_id})
    browser.send_request_and_wait.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('frame_id', INVALID_FRAMES)
async def test_direct_call_rejects_invalid_frame_before_browser_io(browser, frame_id):
    tool = await FoxMCPTools(browser).mcp.get_tool('content_execute_script')
    result = await tool.fn(profile_id=1, tab_id=123, code='42', frame_id=frame_id)
    assert 'frame_id must be a non-negative integer' in result
    browser.send_request_and_wait.assert_not_awaited()


@pytest.mark.asyncio
async def test_frame_discovery_is_advertised_in_actual_tools_list(browser):
    tools = FoxMCPTools(browser)
    async with Client(tools.mcp) as client:
        tool = next(t for t in await client.list_tools() if t.name == 'content_execute_script')
    frame = tool.inputSchema['properties']['frame_id']
    assert frame['type'] == 'integer' and frame['minimum'] == 0 and frame['default'] == 0
    assert 'frame_id' not in tool.inputSchema['required']
    assert 'browser.runtime.getFrameId()' in tool.description
    assert 'window.frames' in tool.description


@pytest.mark.asyncio
@pytest.mark.parametrize('code,message', [
    ('SCRIPT_ERROR', 'No frame with id 42'),
    ('SCRIPT_ERROR', 'Missing host permission for the tab'),
    ('SCRIPT_DENIED', 'Script injection denied for this tab and origin'),
])
async def test_frame_errors_are_reported_without_retry_or_fallback(browser, code, message):
    browser.send_request_and_wait.return_value = {'type': 'error', 'data': {
        'code': code, 'message': message}}
    tool = await FoxMCPTools(browser).mcp.get_tool('content_execute_script')
    result = await tool.fn(profile_id=1, tab_id=123, code='42', frame_id=42)
    assert result == f'Failed to execute script: {message}'
    browser.send_request_and_wait.assert_awaited_once()
