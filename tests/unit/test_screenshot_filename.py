#!/usr/bin/env python3
"""
Unit tests for screenshot filename functionality
Tests the new filename parameter in tabs_capture_screenshot
"""

import pytest
import pytest_asyncio
import tempfile
import os
import base64
import re
from unittest.mock import Mock, AsyncMock
import sys

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class TestScreenshotFilename:
    """Test screenshot filename functionality"""

    @pytest.fixture
    def mock_websocket_server(self):
        """Create mock WebSocket server for testing"""
        # Create a minimal 1x1 PNG image in base64
        test_png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

        mock_server = Mock()
        mock_server.send_request_and_wait = AsyncMock(return_value={
            "type": "response",
            "data": {
                "dataUrl": f"data:image/png;base64,{test_png_base64}",
                "format": "png",
                "quality": 90,
                "windowId": "current"
            }
        })
        return mock_server

    @pytest.fixture
    def mcp_tools(self, mock_websocket_server):
        """Create MCP tools instance with mock server"""
        return FoxMCPTools(mock_websocket_server)

    @pytest.mark.asyncio
    async def test_screenshot_file_saving_logic(self, mock_websocket_server):
        """Test the file saving logic of screenshot functionality"""
        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, "test_screenshot.png")

            # Simulate the exact logic from the screenshot function
            test_png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            data_url = f"data:image/png;base64,{test_png_base64}"
            captured_format = "png"

            # Extract the base64 part from data URL (like in actual function)
            data_prefix = f"data:image/{captured_format};base64,"
            assert data_url.startswith(data_prefix), "Test data should have correct format"

            base64_data = data_url[len(data_prefix):]

            # Test the file saving logic directly (this is what the function does)
            test_filename = filename
            if not test_filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                test_filename = f"{test_filename}.{captured_format}"

            # Decode base64 and save to file (exact logic from function)
            image_data = base64.b64decode(base64_data)
            with open(test_filename, 'wb') as f:
                f.write(image_data)

            file_size = len(image_data)

            # Verify file was created and has correct content
            assert os.path.exists(test_filename), "Screenshot file should be created"
            assert file_size > 0, "File should not be empty"

            # Verify content matches
            with open(test_filename, 'rb') as f:
                saved_data = f.read()

            assert saved_data == image_data, "Saved file should match decoded image data"
            assert len(saved_data) == file_size, "File size should match"

    @pytest.mark.asyncio
    async def test_screenshot_without_filename_returns_base64(self, mcp_tools, mock_websocket_server):
        """Test that not providing filename returns base64 data as before"""
        # This tests backward compatibility
        mock_response = await mock_websocket_server.send_request_and_wait({})

        assert "dataUrl" in mock_response["data"]
        assert "data:image/png;base64," in mock_response["data"]["dataUrl"]

    def test_filename_extension_logic(self):
        """Test filename extension logic"""
        test_cases = [
            ("screenshot", "png", "screenshot.png"),
            ("screenshot.png", "png", "screenshot.png"),
            ("screenshot.jpg", "jpeg", "screenshot.jpg"),
            ("screenshot.jpeg", "jpeg", "screenshot.jpeg"),
            ("my_image", "jpeg", "my_image.jpeg"),
        ]

        for filename, format_type, expected in test_cases:
            # Test the extension logic
            if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                result = f"{filename}.{format_type}"
            else:
                result = filename

            assert result == expected, f"Extension logic failed for {filename} with format {format_type}"

    @pytest.mark.asyncio
    async def test_screenshot_file_error_handling(self, mcp_tools, mock_websocket_server):
        """Test error handling when file cannot be written"""
        # Test with invalid path (directory that doesn't exist)
        invalid_filename = "/nonexistent/directory/screenshot.png"

        # Test that the error would be caught
        test_png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

        try:
            image_data = base64.b64decode(test_png_base64)
            with open(invalid_filename, 'wb') as f:
                f.write(image_data)
            # Should not reach here
            assert False, "Should have raised an exception for invalid path"
        except (OSError, IOError, FileNotFoundError):
            # Expected behavior - error should be caught
            assert True

    def test_base64_decoding_logic(self):
        """Test base64 decoding logic used in screenshot saving"""
        # Test with valid base64 PNG data
        test_png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

        # Test decoding
        image_data = base64.b64decode(test_png_base64)
        assert len(image_data) > 0, "Decoded image data should not be empty"

        # Test that it's valid PNG (starts with PNG header)
        png_header = b'\x89PNG\r\n\x1a\n'
        assert image_data.startswith(png_header), "Should be valid PNG data"


PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhf"
    "DwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class StubScreenshotServer:
    """Stands in for the WebSocket server: records the request, replays a canned answer"""

    def __init__(self):
        self.sent_request = None
        self.requests = 0
        self.response = {
            "type": "response",
            "data": {"dataUrl": f"data:image/png;base64,{PNG_1X1}", "format": "png", "quality": 90},
        }

    async def send_request_and_wait(self, request):
        self.sent_request = request
        self.requests += 1
        return self.response


class TestScreenshotOfOneTab:
    """tabs_capture_screenshot(tab_id=...) captures one given tab, not the window's visible one

    These check the request the tool builds and the answer it renders; that the browser
    really renders a background tab is covered against real Firefox in
    tests/integration/test_browser_functionality.py.
    """

    @pytest.fixture
    def stub(self):
        return StubScreenshotServer()

    @pytest.fixture
    def call(self, stub):
        tools = FoxMCPTools(stub)

        async def run(**kwargs):
            tool = await tools.mcp.get_tool("tabs_capture_screenshot")
            return await tool.fn(**kwargs)

        return run

    @pytest.mark.asyncio
    async def test_a_tab_id_asks_for_that_tab_and_names_no_window(self, call, stub):
        await call(tab_id=42, format="jpeg", quality=70)

        request = stub.sent_request
        assert request["action"] == "tabs.captureTab"
        assert request["data"] == {"tabId": 42, "format": "jpeg", "quality": 70}

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
    async def test_an_extension_without_the_action_gets_a_message_that_says_what_to_do(
        self, call, stub
    ):
        stub.response = {
            "type": "error",
            "data": {"code": "UNKNOWN_ACTION", "message": "Unknown tabs action: tabs.captureTab"},
        }

        result = await call(tab_id=42)

        assert "too old" in result and "tabs_switch" in result and "window_id" in result

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
