"""Tests for capturing a region of a tab and scaling the screenshot"""

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Records the request and replays a canned response"""

    def __init__(self):
        self.sent_request = None
        self.response = {"type": "response", "data": {
            "dataUrl": "data:image/png;base64,AAAA", "format": "png", "quality": 90, "tabId": 4}}

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent_request = request
        return self.response


@pytest.fixture
def stub_server():
    return StubWebSocketServer()


@pytest.fixture
def capture(stub_server):
    tools = FoxMCPTools(stub_server)

    async def call(**kwargs):
        tool = await tools.mcp.get_tool("tabs_capture_screenshot")
        return await tool.fn(**kwargs)

    return call


class TestScreenshotRegion:

    @pytest.mark.asyncio
    async def test_sends_rect_and_scale_for_a_tab(self, capture, stub_server):
        await capture(profile_id=1, tab_id=4, x=10, y=20, width=300, height=100, scale=0.5)

        assert stub_server.sent_request["action"] == "tabs.captureTab"
        data = stub_server.sent_request["data"]
        assert data["rect"] == {"x": 10, "y": 20, "width": 300, "height": 100}
        assert data["scale"] == 0.5

    @pytest.mark.asyncio
    async def test_sends_rect_for_the_visible_tab(self, capture, stub_server):
        await capture(profile_id=1, x=0, y=0, width=50, height=40)

        assert stub_server.sent_request["action"] == "tabs.captureVisibleTab"
        assert stub_server.sent_request["data"]["rect"]["width"] == 50

    @pytest.mark.asyncio
    async def test_without_region_nothing_extra_is_sent(self, capture, stub_server):
        await capture(profile_id=1, tab_id=4)

        assert "rect" not in stub_server.sent_request["data"]
        assert "scale" not in stub_server.sent_request["data"]

    @pytest.mark.asyncio
    async def test_incomplete_region_sends_nothing(self, capture, stub_server):
        result = await capture(profile_id=1, x=10, y=20)

        assert "together" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_empty_region_or_scale_sends_nothing(self, capture, stub_server):
        empty = await capture(profile_id=1, x=0, y=0, width=0, height=10)
        scaled = await capture(profile_id=1, scale=0)

        assert "positive" in empty and "positive" in scaled
        assert stub_server.sent_request is None
