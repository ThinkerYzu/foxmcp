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
        assert stub_server.sent_request["data"]["rect"] == {
            "x": 0, "y": 0, "width": 50, "height": 40}

    @pytest.mark.asyncio
    async def test_region_with_window_id(self, capture, stub_server):
        await capture(profile_id=1, window_id=7, x=1, y=2, width=3, height=4, scale=1)

        data = stub_server.sent_request["data"]
        assert data["windowId"] == 7
        assert data["rect"] == {"x": 1, "y": 2, "width": 3, "height": 4}
        assert data["scale"] == 1.0

    @pytest.mark.asyncio
    async def test_region_is_refused_together_with_tab_and_window(self, capture, stub_server):
        result = await capture(profile_id=1, tab_id=4, window_id=7, x=0, y=0, width=5, height=5)

        assert "not both" in result
        assert stub_server.sent_request is None

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
    async def test_empty_region_sends_nothing(self, capture, stub_server):
        result = await capture(profile_id=1, x=0, y=0, width=0, height=10)

        assert "positive" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_negative_origin_sends_nothing(self, capture, stub_server):
        result = await capture(profile_id=1, x=-1, y=0, width=10, height=10)

        assert "must not be negative" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [1.5, True, "10"])
    async def test_region_values_must_be_integers(self, capture, stub_server, bad):
        result = await capture(profile_id=1, x=0, y=0, width=bad, height=10)

        assert "must be integers" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [0, -0.5, 4.5, float("nan"), float("inf")])
    async def test_scale_must_be_above_zero_and_at_most_four(self, capture, stub_server, bad):
        result = await capture(profile_id=1, scale=bad)

        assert "above 0 and at most 4" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [True, "0.5"])
    async def test_scale_must_be_a_number(self, capture, stub_server, bad):
        result = await capture(profile_id=1, scale=bad)

        assert "must be a number" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("good", [0.25, 1, 2, 4])
    async def test_scales_up_to_four_are_allowed(self, capture, stub_server, good):
        await capture(profile_id=1, scale=good)

        assert stub_server.sent_request["data"]["scale"] == float(good)

    @pytest.mark.asyncio
    async def test_a_region_without_scale_omits_scale(self, capture, stub_server):
        await capture(profile_id=1, x=0, y=0, width=400, height=200)

        assert "scale" not in stub_server.sent_request["data"]
        assert stub_server.sent_request["data"]["rect"] == {
            "x": 0, "y": 0, "width": 400, "height": 200}


class TestRefusedByTheExtension:

    @pytest.mark.asyncio
    async def test_the_extension_refusal_reaches_the_client(self, capture, stub_server):
        message = ("The screenshot is 1500000 characters as a data URL, over the 1000000 "
                   "the connection to the server can carry; use jpeg, a lower quality or "
                   "scale, or a smaller region")
        stub_server.response = {"type": "error", "data": {
            "code": "CAPTURE_ERROR", "message": message}}

        result = await capture(profile_id=1, tab_id=4, x=0, y=0, width=1470, height=3000, scale=4)

        assert result == f"Failed to capture screenshot: {message}"
