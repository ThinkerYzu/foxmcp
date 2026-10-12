"""
Tests for the page interaction tools: content_snapshot, content_click,
content_type and content_press_key

These stub the WebSocket server, so they check the request each tool builds and
how it renders the extension's answer. The events the content script dispatches
are exercised against real Firefox, where a stub could not tell a click that
opens a mousedown menu from one that does not.
"""

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Records the request and replays a canned response"""

    def __init__(self):
        self.sent_request = None
        self.response = {"type": "response", "data": {}}

    async def send_request_and_wait(self, request):
        self.sent_request = request
        return self.response


@pytest.fixture
def stub_server():
    return StubWebSocketServer()


@pytest.fixture
def call_tool(stub_server):
    tools = FoxMCPTools(stub_server)

    async def call(name, **kwargs):
        tool = await tools.mcp.get_tool(name)
        return await tool.fn(**kwargs)

    return call


class TestSnapshot:

    @pytest.mark.asyncio
    async def test_lists_elements_under_the_page_title(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {
            "title": "Form", "url": "https://example.org/form",
            "snapshot": '[r1] input "Name" (type=text)\n[r2] button "Save"'}}

        result = await call_tool("content_snapshot", tab_id=4)

        assert stub_server.sent_request["action"] == "content.snapshot"
        assert stub_server.sent_request["data"] == {"tabId": 4, "maxElements": 300}
        assert result.startswith("Snapshot of Form (https://example.org/form):")
        assert '[r2] button "Save"' in result


class TestClick:

    @pytest.mark.asyncio
    async def test_sends_the_ref(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"clicked": '[r2] button "Save"'}}

        result = await call_tool("content_click", tab_id=4, ref="r2")

        assert stub_server.sent_request["action"] == "content.click"
        assert stub_server.sent_request["data"] == {"tabId": 4, "ref": "r2", "selector": None}
        assert result == 'Clicked [r2] button "Save"'

    @pytest.mark.asyncio
    async def test_requires_a_target(self, call_tool, stub_server):
        with pytest.raises(ValueError, match="ref"):
            await call_tool("content_click", tab_id=4)
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_reports_a_stale_ref(self, call_tool, stub_server):
        stub_server.response = {"type": "error", "data": {
            "message": "No element with ref r9; take a new snapshot"}}

        result = await call_tool("content_click", tab_id=4, ref="r9")

        assert result == "Failed to click: No element with ref r9; take a new snapshot"


class TestType:

    @pytest.mark.asyncio
    async def test_replaces_by_default_and_can_submit(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"typed": '[r1] input "Dor"'}}

        await call_tool("content_type", tab_id=4, selector="#name", text="Dor", submit=True)

        assert stub_server.sent_request["action"] == "content.type"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "ref": None, "selector": "#name",
            "text": "Dor", "clear": True, "submit": True}


class TestPressKey:

    @pytest.mark.asyncio
    async def test_targets_the_focused_element_when_none_given(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"pressed": "Escape"}}

        result = await call_tool("content_press_key", tab_id=4, key="Escape")

        assert stub_server.sent_request["action"] == "content.press_key"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "key": "Escape", "ref": None, "selector": None}
        assert result == "Pressed Escape"
