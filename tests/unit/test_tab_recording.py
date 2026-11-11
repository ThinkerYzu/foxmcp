"""Tests for recording a tab to a receiver on this machine"""

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
def call(stub_server):
    tools = FoxMCPTools(stub_server)

    async def run(name, **kwargs):
        tool = await tools.mcp.get_tool(name)
        return await tool.fn(**kwargs)

    return run


URL = "http://127.0.0.1:8099/frames"


class TestRecordStart:

    @pytest.mark.asyncio
    async def test_sends_the_url_and_the_settings(self, call, stub_server):
        stub_server.response = {"type": "response", "data": {
            "recordingId": "rec-4", "url": URL, "intervalMs": 250, "maxFrames": 10}}

        result = await call("tabs_record_start", profile_id=1, tab_id=4, url=URL,
                            interval_ms=250, max_frames=10)

        assert stub_server.sent_request["action"] == "tabs.record_start"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "url": URL, "intervalMs": 250, "maxFrames": 10, "scale": 0.5, "quality": 50}
        assert result == (f"Recording tab 4 as rec-4 to {URL}: a frame every 250 ms, "
                          "up to 10 frames")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:8099/", "https://localhost:8443/frames", "ws://[::1]:9000/",
        "wss://127.0.0.1/stream", "ws://localhost:9000"])
    async def test_local_addresses_are_accepted(self, call, stub_server, url):
        stub_server.response = {"type": "response", "data": {"recordingId": "rec-4", "url": url}}

        await call("tabs_record_start", profile_id=1, tab_id=4, url=url)

        assert stub_server.sent_request["data"]["url"] == url

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url, message", [
        ("http://example.org/frames", "must point to this machine"),
        ("http://192.168.1.5:8099/", "must point to this machine"),
        ("http://127.0.0.1.example.org/", "must point to this machine"),
        ("http://0.0.0.0:8099/", "must point to this machine"),
        ("ftp://127.0.0.1/", "must start with"),
        ("file:///tmp/frames", "must start with"),
        ("127.0.0.1:8099", "must start with"),
        ("http://user:secret@127.0.0.1:8099/", "must not carry credentials"),
        ("http://127.0.0.1:notaport/", "must be a valid URL"),
        ("", "nonempty string"),
        ("   ", "nonempty string"),
        (None, "nonempty string"),
        (8099, "nonempty string"),
    ])
    async def test_other_addresses_are_refused_before_anything_is_sent(
            self, call, stub_server, url, message):
        result = await call("tabs_record_start", profile_id=1, tab_id=4, url=url)

        assert result.startswith("Failed to start recording: ") and message in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("arguments, name", [
        ({"interval_ms": 99}, "interval_ms"),
        ({"interval_ms": 5001}, "interval_ms"),
        ({"interval_ms": 250.5}, "interval_ms"),
        ({"interval_ms": True}, "interval_ms"),
        ({"max_frames": 0}, "max_frames"),
        ({"max_frames": 301}, "max_frames"),
        ({"quality": 0}, "quality"),
        ({"quality": 101}, "quality"),
        ({"quality": "50"}, "quality"),
    ])
    async def test_integer_arguments_are_checked(self, call, stub_server, arguments, name):
        result = await call("tabs_record_start", profile_id=1, tab_id=4, url=URL, **arguments)

        assert result.startswith(f"Failed to start recording: {name} must be an integer")
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scale", [0, -0.5, 1.5, float("nan"), float("inf"), True, "0.5"])
    async def test_scale_must_be_above_zero_and_at_most_one(self, call, stub_server, scale):
        result = await call("tabs_record_start", profile_id=1, tab_id=4, url=URL, scale=scale)

        assert result == ("Failed to start recording: "
                          "scale must be a finite number above 0 and at most 1")
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_reports_a_receiver_that_is_not_there(self, call, stub_server):
        stub_server.response = {"type": "error", "data": {
            "code": "API_ERROR",
            "message": f"Cannot record tab 4 to {URL}: the receiver answered HTTP 500"}}

        result = await call("tabs_record_start", profile_id=1, tab_id=4, url=URL)

        assert result == ("Failed to start recording: "
                          f"Cannot record tab 4 to {URL}: the receiver answered HTTP 500")


class TestRecordStop:

    @pytest.mark.asyncio
    async def test_reports_the_frames_that_were_sent(self, call, stub_server):
        stub_server.response = {"type": "response", "data": {
            "frames": 12, "skipped": 0, "durationMs": 6100, "error": None}}

        result = await call("tabs_record_stop", profile_id=1, recording_id="rec-4")

        assert stub_server.sent_request["action"] == "tabs.record_stop"
        assert stub_server.sent_request["data"] == {"recordingId": "rec-4"}
        assert result == "Recording rec-4 stopped: 12 frame(s) sent in 6100 ms"

    @pytest.mark.asyncio
    async def test_reports_skipped_frames_and_an_early_end(self, call, stub_server):
        stub_server.response = {"type": "response", "data": {
            "frames": 3, "skipped": 2, "durationMs": 900,
            "error": "the receiver closed the connection"}}

        result = await call("tabs_record_stop", profile_id=1, recording_id="rec-4")

        assert result == ("Recording rec-4 stopped: 3 frame(s) sent in 900 ms, "
                          "2 skipped because the receiver was slow; "
                          "it ended early: the receiver closed the connection")

    @pytest.mark.asyncio
    async def test_reports_an_unknown_recording(self, call, stub_server):
        stub_server.response = {"type": "error", "data": {
            "code": "RECORDING_NOT_FOUND", "message": "No recording rec-9"}}

        result = await call("tabs_record_stop", profile_id=1, recording_id="rec-9")

        assert result == "Failed to stop recording: No recording rec-9"
