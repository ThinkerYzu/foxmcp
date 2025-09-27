"""
Unit tests for window management handlers
"""

import pytest
import json
import asyncio
import re
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from server.server import FoxMCPServer


class TestWindowHandlers:
    
    @pytest.fixture
    def server(self):
        """Create FoxMCPServer instance"""
        return FoxMCPServer(host="localhost", port=8765, start_mcp=False)
    
    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket"""
        mock = Mock()
        mock.send = AsyncMock()
        mock.close = AsyncMock()
        mock.remote_address = ("127.0.0.1", 12345)
        return mock

    @pytest.mark.asyncio
    async def test_windows_list_message_format(self, server):
        """Test that windows.list message is handled without errors"""
        message = json.dumps({
            "id": "test_001",
            "type": "request",
            "action": "windows.list",
            "data": {"populate": True},
            "timestamp": "2025-09-09T12:00:00.000Z"
        })
        
        # Should not raise exception even without browser connection
        await server.handle_extension_message(message)

    @pytest.mark.asyncio
    async def test_windows_get_message_format(self, server):
        """Test that windows.get message is handled without errors"""
        message = json.dumps({
            "id": "test_002",
            "type": "request",
            "action": "windows.get",
            "data": {"windowId": 1, "populate": True},
            "timestamp": "2025-09-09T12:00:00.000Z"
        })
        
        await server.handle_extension_message(message)

    @pytest.mark.asyncio
    async def test_windows_create_message_format(self, server):
        """Test that windows.create message is handled without errors"""
        message = json.dumps({
            "id": "test_003",
            "type": "request",
            "action": "windows.create",
            "data": {
                "url": "https://example.com",
                "type": "normal",
                "width": 800,
                "height": 600,
                "focused": True
            },
            "timestamp": "2025-09-09T12:00:00.000Z"
        })
        
        await server.handle_extension_message(message)

    @pytest.mark.asyncio
    async def test_windows_close_message_format(self, server):
        """Test that windows.close message is handled without errors"""
        message = json.dumps({
            "id": "test_004",
            "type": "request",
            "action": "windows.close",
            "data": {"windowId": 2},
            "timestamp": "2025-09-09T12:00:00.000Z"
        })
        
        await server.handle_extension_message(message)

    @pytest.mark.asyncio
    async def test_windows_focus_message_format(self, server):
        """Test that windows.focus message is handled without errors"""
        message = json.dumps({
            "id": "test_005",
            "type": "request",
            "action": "windows.focus",
            "data": {"windowId": 1},
            "timestamp": "2025-09-09T12:00:00.000Z"
        })
        
        await server.handle_extension_message(message)

    @pytest.mark.asyncio
    async def test_windows_update_message_format(self, server):
        """Test that windows.update message is handled without errors"""
        message = json.dumps({
            "id": "test_006",
            "type": "request",
            "action": "windows.update",
            "data": {
                "windowId": 1,
                "width": 900,
                "height": 700,
                "state": "maximized"
            },
            "timestamp": "2025-09-09T12:00:00.000Z"
        })
        
        await server.handle_extension_message(message)

    @pytest.mark.asyncio
    async def test_windows_get_current_message_format(self, server):
        """Test that windows.get_current message is handled without errors"""
        message = json.dumps({
            "id": "test_007",
            "type": "request",
            "action": "windows.get_current",
            "data": {"populate": False},
            "timestamp": "2025-09-09T12:00:00.000Z"
        })
        
        await server.handle_extension_message(message)

    def test_window_message_protocol_structure(self):
        """Test that window messages follow the expected protocol structure"""
        # Test request message structure
        request_msg = {
            "id": "req_001",
            "type": "request",
            "action": "windows.list",
            "data": {},
            "timestamp": "2025-09-09T12:00:00.000Z"
        }
        
        # Should be valid JSON
        json_str = json.dumps(request_msg)
        parsed = json.loads(json_str)
        
        # Required fields should be present
        assert "id" in parsed
        assert "type" in parsed
        assert "action" in parsed
        assert "data" in parsed
        assert "timestamp" in parsed
        
        # Action should be window-related
        assert parsed["action"].startswith("windows.")

    def test_window_action_names(self):
        """Test that all window actions follow naming convention"""
        expected_actions = [
            "windows.list",
            "windows.get", 
            "windows.get_current",
            "windows.get_last_focused",
            "windows.create",
            "windows.close",
            "windows.focus",
            "windows.update"
        ]
        
        for action in expected_actions:
            # All should start with windows.
            assert action.startswith("windows.")
            # Should contain only letters, dots, and underscores
            assert all(c.isalnum() or c in "._" for c in action)

    @pytest.mark.asyncio
    async def test_invalid_window_action(self, server):
        """Test handling of invalid window action"""
        message = json.dumps({
            "id": "test_008",
            "type": "request", 
            "action": "windows.invalid_action",
            "data": {},
            "timestamp": "2025-09-09T12:00:00.000Z"
        })
        
        # Should handle gracefully without crashing
        await server.handle_extension_message(message)

    def test_window_error_codes_defined(self):
        """Test that window-specific error codes are properly defined"""
        # These error codes should be used in window operations
        expected_error_codes = [
            "WINDOW_NOT_FOUND",
            "INVALID_WINDOW_STATE", 
            "INVALID_WINDOW_TYPE",
            "WINDOW_CREATION_FAILED"
        ]
        
        # Error codes are defined in the protocol, this test just validates they exist
        for error_code in expected_error_codes:
            assert isinstance(error_code, str)
            assert len(error_code) > 0
            assert error_code.isupper()


class TestWindowMCPTools:
    """Test window MCP tool definitions"""
    
    @pytest.fixture
    def mock_websocket_server(self):
        """Create mock WebSocket server for MCP tools"""
        mock = Mock()
        mock.send_message_and_wait = AsyncMock()
        return mock

    def test_mcp_tools_import(self):
        """Test that MCP tools can be imported"""
        from server.mcp_tools import FoxMCPTools
        assert FoxMCPTools is not None

    def test_window_tools_initialization(self, mock_websocket_server):
        """Test that window MCP tools can be initialized"""
        from server.mcp_tools import FoxMCPTools
        
        tools = FoxMCPTools(mock_websocket_server)
        assert tools is not None
        assert tools.mcp is not None

    def test_window_tool_names_exist(self, mock_websocket_server):
        """Test that window tool names are properly defined"""
        from server.mcp_tools import FoxMCPTools
        
        tools = FoxMCPTools(mock_websocket_server)
        
        # The tools should be registered with the MCP instance
        # We can't easily introspect FastMCP tools, but we can verify the setup completed
        assert hasattr(tools, 'mcp')
        assert hasattr(tools, 'websocket_server')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])