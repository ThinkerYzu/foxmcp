"""Tests for recording a tab and assembling the frames into a GIF"""

import base64
import io

import pytest
from PIL import Image

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools, assemble_recording


def jpeg(color):
    out = io.BytesIO()
    Image.new("RGB", (8, 6), color).save(out, "JPEG")
    return out.getvalue()


class StubWebSocketServer:
    """Records the request and replays a canned response"""

    def __init__(self):
        self.sent_request = None
        self.response = {"type": "response", "data": {}}

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent_request = request
        return self.response


class FrameServer:
    """Plays the extension's recording requests with canned frames"""

    def __init__(self, frames):
        self.frames = frames
        self.actions = []

    async def send_request_and_wait(self, request, timeout=30.0):
        action = request["action"]
        self.actions.append(action)
        if action == "tabs.record_stop":
            return {"type": "response", "data": {"frames": len(self.frames), "error": None}}
        if action == "tabs.record_frame":
            data = self.frames[request["data"]["index"]]
            url = "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")
            return {"type": "response", "data": {"dataUrl": url, "delayMs": 500}}
        return {"type": "response", "data": {"discarded": True}}


async def call(server, name, **kwargs):
    tool = await FoxMCPTools(server).mcp.get_tool(name)
    return await tool.fn(**kwargs)


class TestRecordStart:

    @pytest.mark.asyncio
    async def test_sends_the_settings(self):
        stub = StubWebSocketServer()
        stub.response = {"type": "response", "data": {
            "recordingId": "rec-4", "intervalMs": 250, "maxFrames": 10}}

        result = await call(stub, "tabs_record_start", profile_id=1, tab_id=4,
                            interval_ms=250, max_frames=10)

        assert stub.sent_request["action"] == "tabs.record_start"
        assert stub.sent_request["data"] == {
            "tabId": 4, "intervalMs": 250, "maxFrames": 10, "scale": 0.5, "quality": 50}
        assert result == "Recording tab 4 as rec-4: a frame every 250 ms, up to 10 frames"

    @pytest.mark.asyncio
    async def test_reports_a_tab_that_cannot_be_captured(self):
        stub = StubWebSocketServer()
        stub.response = {"type": "error", "data": {"message": "Cannot record tab 4"}}

        result = await call(stub, "tabs_record_start", profile_id=1, tab_id=4)

        assert result == "Failed to start recording: Cannot record tab 4"


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
    async def test_integer_arguments_are_checked(self, arguments, name):
        stub = StubWebSocketServer()

        result = await call(stub, "tabs_record_start", profile_id=1, tab_id=4, **arguments)

        assert result.startswith(f"Failed to start recording: {name} must be an integer")
        assert stub.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("scale", [0, -0.5, 1.5, float("nan"), float("inf"), True, "0.5"])
    async def test_scale_must_be_above_zero_and_at_most_one(self, scale):
        stub = StubWebSocketServer()

        result = await call(stub, "tabs_record_start", profile_id=1, tab_id=4, scale=scale)

        assert result == "Failed to start recording: scale must be a number above 0 and at most 1"
        assert stub.sent_request is None


class TestRecordStop:

    @pytest.mark.asyncio
    async def test_builds_a_gif_and_merges_repeats(self, tmp_path):
        red, blue = jpeg("red"), jpeg("blue")
        server = FrameServer([red, red, blue])

        result = await call(server, "tabs_record_stop", profile_id=1, recording_id="rec-4",
                            filename=str(tmp_path / "out" / "demo"))

        gif = tmp_path / "out" / "demo.gif"
        assert gif.exists()
        assert "3 frame(s) (2 distinct)" in result
        with Image.open(gif) as image:
            assert image.n_frames == 2
        assert server.actions == ["tabs.record_stop", "tabs.record_frame", "tabs.record_frame",
                                  "tabs.record_frame", "tabs.record_discard"]

    @pytest.mark.asyncio
    async def test_reports_an_unknown_recording(self):
        stub = StubWebSocketServer()
        stub.response = {"type": "error", "data": {"message": "No recording rec-9"}}

        result = await call(stub, "tabs_record_stop", profile_id=1, recording_id="rec-9",
                            filename="x.gif")

        assert result == "Failed to stop recording: No recording rec-9"


    @pytest.mark.asyncio
    async def test_a_failed_frame_read_still_discards_the_recording(self, tmp_path):
        class FailingFrames(FrameServer):
            async def send_request_and_wait(self, request, timeout=30.0):
                if request["action"] == "tabs.record_frame":
                    self.actions.append(request["action"])
                    return {"type": "error", "data": {"message": "No frame 0 in recording rec-4"}}
                return await super().send_request_and_wait(request, timeout)

        server = FailingFrames([jpeg("red")])

        result = await call(server, "tabs_record_stop", profile_id=1, recording_id="rec-4",
                            filename=str(tmp_path / "demo.gif"))

        assert result == "Failed to read frame 0: No frame 0 in recording rec-4"
        assert server.actions[-1] == "tabs.record_discard"

    @pytest.mark.asyncio
    async def test_filename_must_not_be_empty(self):
        stub = StubWebSocketServer()

        result = await call(stub, "tabs_record_stop", profile_id=1, recording_id="rec-4", filename=" ")

        assert result == "Failed to save the recording: filename must be a non-empty string"
        assert stub.sent_request is None


class TestAssemble:

    def test_without_pillow_frames_are_saved_as_files(self, tmp_path, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "PIL", None)

        result = assemble_recording([(b"one", 500), (b"two", 500), (b"two", 500)],
                                    str(tmp_path / "demo.gif"))

        assert "Pillow is not installed" in result
        assert sorted(p.name for p in (tmp_path / "demo").iterdir()) == ["frame-000.jpg", "frame-001.jpg"]

    def test_no_frames_is_an_error(self, tmp_path):
        with pytest.raises(ValueError, match="no frames"):
            assemble_recording([], str(tmp_path / "demo.gif"))
