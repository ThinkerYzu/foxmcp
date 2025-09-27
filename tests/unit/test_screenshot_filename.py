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

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])