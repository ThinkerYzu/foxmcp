"""Tests for content_read_console"""

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Records the request and replays a canned response"""

    def __init__(self):
        self.sent_request = None
        self.response = {"type": "response", "data": {}}

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent_request = request
        return self.response


@pytest.fixture
def stub_server():
    return StubWebSocketServer()


@pytest.fixture
def read_console(stub_server):
    tools = FoxMCPTools(stub_server)

    async def call(**kwargs):
        tool = await tools.mcp.get_tool("content_read_console")
        return await tool.fn(**kwargs)

    return call


class TestConsole:

    @pytest.mark.asyncio
    async def test_first_call_only_starts_recording(self, read_console, stub_server):
        stub_server.response = {"type": "response", "data": {"started": True, "entries": []}}

        result = await read_console(profile_id=1, tab_id=4)

        assert stub_server.sent_request["action"] == "content.console"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "level": None, "pattern": None, "limit": 50, "clear": False}
        assert result.startswith("Console recording started")

    @pytest.mark.asyncio
    async def test_lists_entries_with_their_level(self, read_console, stub_server):
        stub_server.response = {"type": "response", "data": {"started": False, "entries": [
            {"level": "error", "message": "boom"}, {"level": "uncaught", "message": "x is not defined"}]}}

        result = await read_console(profile_id=1, tab_id=4, level="error", pattern="x")

        assert stub_server.sent_request["data"]["level"] == "error"
        assert stub_server.sent_request["data"]["pattern"] == "x"
        assert result == "[error] boom\n[uncaught] x is not defined"

    @pytest.mark.asyncio
    async def test_reports_an_empty_console(self, read_console, stub_server):
        stub_server.response = {"type": "response", "data": {"started": False, "entries": []}}

        assert await read_console(profile_id=1, tab_id=4) == "No console entries"

    @pytest.mark.asyncio
    async def test_reports_an_extension_error(self, read_console, stub_server):
        stub_server.response = {"type": "error", "data": {"message": "Tab not found"}}

        result = await read_console(profile_id=1, tab_id=4)

        assert result == "Failed to read the console: Tab not found"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("arguments, message", [
        ({"level": "loud"}, "level"),
        ({"level": 3}, "level"),
        ({"pattern": 1}, "pattern"),
        ({"limit": 0}, "limit"),
        ({"limit": 501}, "limit"),
        ({"limit": True}, "limit"),
        ({"limit": "5"}, "limit"),
        ({"clear": "yes"}, "clear"),
    ])
    async def test_arguments_are_checked(self, read_console, stub_server, arguments, message):
        with pytest.raises(ValueError, match=message):
            await read_console(profile_id=1, tab_id=4, **arguments)
        assert stub_server.sent_request is None
