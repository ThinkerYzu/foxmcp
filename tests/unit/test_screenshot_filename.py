"""Screenshot file/preview output and target routing use required binary uploads."""

import asyncio
import base64
import os
import tempfile

import pytest

import test_imports  # noqa: F401
from server.file_transfer import FileTransferServer
from server.mcp_tools import FoxMCPTools
from test_upload_transfer import put


PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhf"
    "DwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class StubScreenshotServer:
    """Record control requests and upload canned bytes through actual HTTP."""

    def __init__(self):
        self.file_transfers = FileTransferServer()
        self.sent_request = None
        self.requests = 0
        self.response = {"type": "response", "data": {"quality": 90}}

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent_request = request
        self.requests += 1
        if self.response.get("type") == "response":
            upload = request["data"]["upload"]
            image = base64.b64decode(PNG_1X1)
            image_format = request["data"]["format"]
            mime_type = f"image/{image_format}"
            status = await asyncio.to_thread(put, upload["url"], image, upload["requestId"],
                                             **{"Content-Type": mime_type})
            assert status == 204
            self.response["data"].update({"format": image_format, "upload": {
                "requestId": upload["requestId"], "size": len(image), "type": mime_type}})
        return self.response


@pytest.fixture
def screenshot():
    server = StubScreenshotServer()
    tools = FoxMCPTools(server, file_transfers=server.file_transfers)
    yield server, tools
    server.file_transfers.close()


class TestScreenshotFilename:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("filename, image_format, output", [
        ("capture", "png", "capture.png"),
        ("capture.png", "png", "capture.png"),
        ("capture.jpg", "jpeg", "capture.jpg"),
        ("capture.jpeg", "jpeg", "capture.jpeg"),
        ("capture", "jpeg", "capture.jpeg"),
    ])
    async def test_uploaded_file_and_extension(self, screenshot, tmp_path,
                                               filename, image_format, output):
        server, tools = screenshot
        tool = await tools.mcp.get_tool("tabs_capture_screenshot")
        result = await tool.fn(profile_id=1, filename=str(tmp_path / filename), format=image_format)
        assert result.startswith("Screenshot saved to"), result
        assert (tmp_path / output).read_bytes() == base64.b64decode(PNG_1X1)
        assert not server.file_transfers._uploads
        assert not list(tmp_path.glob('.foxmcp-upload-*'))

    @pytest.mark.asyncio
    async def test_without_filename_returns_generated_preview_and_cleans_up(self, screenshot):
        server, tools = screenshot
        tool = await tools.mcp.get_tool("tabs_capture_screenshot")
        result = await tool.fn(profile_id=1)
        assert ("data:image/png;base64," + PNG_1X1)[:100] in result
        assert f"Base64 data size: {len(PNG_1X1)} characters" in result
        assert not server.file_transfers._uploads

    @pytest.mark.asyncio
    async def test_missing_output_directory_is_refused_before_capture(self, screenshot, tmp_path):
        server, tools = screenshot
        tool = await tools.mcp.get_tool("tabs_capture_screenshot")
        result = await tool.fn(profile_id=1, filename=str(tmp_path / 'missing' / 'capture.png'))
        assert result.startswith("Error capturing screenshot:"), result
        assert server.requests == 0
        assert not server.file_transfers._uploads


class TestScreenshotOfOneTab:
    """tabs_capture_screenshot(tab_id=...) captures one given tab, not the window's visible one

    These check the request the tool builds and the answer it renders; that the browser
    really renders a background tab is covered against real Firefox in
    tests/integration/test_browser_functionality.py.
    """

    @pytest.fixture
    def stub(self):
        server = StubScreenshotServer()
        yield server
        server.file_transfers.close()

    @pytest.fixture
    def call(self, stub):
        tools = FoxMCPTools(stub, file_transfers=stub.file_transfers)

        async def run(**kwargs):
            tool = await tools.mcp.get_tool("tabs_capture_screenshot")
            return await tool.fn(profile_id=1, **kwargs)

        return run

    @pytest.mark.asyncio
    async def test_a_tab_id_asks_for_that_tab_and_names_no_window(self, call, stub):
        await call(tab_id=42, format="jpeg", quality=70)

        request = stub.sent_request
        assert request["action"] == "tabs.captureTab"
        assert {key: value for key, value in request["data"].items() if key != "upload"} == {
            "tabId": 42, "format": "jpeg", "quality": 70}
        assert request["data"]["upload"]["requestId"] == request["id"]

    @pytest.mark.asyncio
    async def test_without_a_tab_id_it_is_still_the_visible_tab_of_a_window(self, call, stub):
        await call()
        assert stub.sent_request["action"] == "tabs.captureVisibleTab"
        assert "windowId" not in stub.sent_request["data"]
        assert "tabId" not in stub.sent_request["data"]

        await call(window_id=7)
        assert stub.sent_request["action"] == "tabs.captureVisibleTab"
        assert stub.sent_request["data"]["windowId"] == 7

    @pytest.mark.asyncio
    @pytest.mark.parametrize("window_id", [0, 7])
    async def test_a_tab_id_and_a_window_id_together_are_refused_before_asking_the_browser(
        self, call, stub, window_id
    ):
        result = await call(tab_id=42, window_id=window_id)

        assert "not both" in result
        assert stub.requests == 0

    @pytest.mark.asyncio
    async def test_the_answer_says_which_tab_it_came_from(self, call, stub):
        stub.response["data"]["tabId"] = 42

        inline = await call(tab_id=42)
        assert "Screenshot captured successfully from tab 42" in inline

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "background.png")
            saved = await call(tab_id=42, filename=path)
            assert f"Screenshot saved to '{path}' (tab 42," in saved
            with open(path, "rb") as f:
                assert f.read().startswith(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_the_answer_for_a_window_still_says_window(self, call, stub):
        stub.response["data"]["windowId"] = 7
        assert "from window 7" in await call(window_id=7)

    @pytest.mark.asyncio
    async def test_unknown_actions_return_the_extension_error(
        self, call, stub
    ):
        stub.response = {
            "type": "error",
            "data": {"code": "UNKNOWN_ACTION", "message": "Unknown tabs action: tabs.captureTab"},
        }

        result = await call(tab_id=42)

        assert result == "Failed to capture screenshot: Unknown tabs action: tabs.captureTab"

    @pytest.mark.asyncio
    async def test_other_errors_pass_the_extensions_message_through(self, call, stub):
        stub.response = {
            "type": "error",
            "data": {"code": "CAPTURE_ERROR", "message": "Failed: No tab with id 42"},
        }

        result = await call(tab_id=42)

        assert "No tab with id 42" in result and "too old" not in result

    @pytest.mark.asyncio
    async def test_an_unknown_action_is_not_blamed_on_the_extension_for_a_window_capture(
        self, call, stub
    ):
        stub.response = {
            "type": "error",
            "data": {"code": "UNKNOWN_ACTION", "message": "Unknown tabs action: x"},
        }

        assert "too old" not in await call(window_id=7)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
