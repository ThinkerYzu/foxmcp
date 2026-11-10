"""Tests for content_wait"""

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Records the request and replays a canned response"""

    def __init__(self):
        self.sent_request = None
        self.timeout = None
        self.response = {"type": "response", "data": {}}

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent_request = request
        self.timeout = timeout
        return self.response


@pytest.fixture
def stub_server():
    return StubWebSocketServer()


@pytest.fixture
def wait(stub_server):
    tools = FoxMCPTools(stub_server)

    async def call(**kwargs):
        tool = await tools.mcp.get_tool("content_wait")
        return await tool.fn(**kwargs)

    return call


class TestWait:

    @pytest.mark.asyncio
    async def test_sends_what_to_wait_for(self, wait, stub_server):
        stub_server.response = {"type": "response", "data": {
            "waitedMs": 420, "url": "https://example.org/done", "title": "Done"}}

        result = await wait(profile_id=1, tab_id=4, selector="#ok", text="Saved", timeout=5, gone=True)

        assert stub_server.sent_request["action"] == "content.wait"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "selector": "#ok", "text": "Saved", "url": None,
            "state": "absent", "timeoutMs": 5000}
        assert result == "Ready after 420 ms: Done (https://example.org/done)"

    @pytest.mark.asyncio
    async def test_waits_for_the_page_alone_by_default(self, wait, stub_server):
        stub_server.response = {"type": "response", "data": {"waitedMs": 0, "url": "u", "title": "t"}}

        await wait(profile_id=1, tab_id=4, url="/done")

        assert stub_server.sent_request["data"]["state"] == "present"
        assert stub_server.sent_request["data"]["timeoutMs"] == 10000

    @pytest.mark.asyncio
    async def test_server_timeout_outlasts_the_wait(self, wait, stub_server):
        await wait(profile_id=1, tab_id=4, timeout=500)

        assert stub_server.timeout > 120.0

    @pytest.mark.asyncio
    async def test_reports_a_timeout(self, wait, stub_server):
        stub_server.response = {"type": "error", "data": {
            "message": "Timed out after 1000 ms: it did not appear"}}

        result = await wait(profile_id=1, tab_id=4, selector="#ok", timeout=1)

        assert result == "Failed to wait: Timed out after 1000 ms: it did not appear"
