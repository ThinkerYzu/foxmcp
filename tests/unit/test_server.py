"""
Unit tests for WebSocket server
"""

import pytest
import json
import asyncio
import re
from unittest.mock import AsyncMock, Mock, patch
from server.server import FoxMCPServer

class TestFoxMCPServer:
    
    @pytest.fixture
    def server(self):
        """Create FoxMCPServer instance"""
        return FoxMCPServer(host="localhost", port=8765)
    
    def test_server_initialization(self, server):
        """Test server initialization"""
        assert server.host == "localhost"
        assert isinstance(server.port, int)  # Port should be an integer (dynamic in tests)
        assert server.port > 0  # Port should be positive
        assert server.extension_connection is None
    
    @pytest.mark.asyncio
    async def test_handle_extension_connection_success(self, server, mock_websocket):
        """Test successful extension connection handling"""
        async def mock_aiter():
            return
            yield  # Make this a generator
            
        mock_websocket.__aiter__ = mock_aiter
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        
        await server.handle_extension_connection(mock_websocket)
        
        assert server.extension_connection is None  # Should be None after connection ends
    
    @pytest.mark.asyncio 
    async def test_handle_extension_message_valid_json(self, server):
        """Test handling valid JSON message from extension"""
        message = json.dumps({
            "id": "test_001",
            "type": "response", 
            "action": "tabs.list",
            "data": {"tabs": []}
        })
        
        # Should not raise exception
        await server.handle_extension_message(message)
    
    @pytest.mark.asyncio
    async def test_handle_extension_message_invalid_json(self, server):
        """Test handling invalid JSON message"""
        invalid_message = "invalid json{"
        
        # Should handle gracefully without raising exception
        await server.handle_extension_message(invalid_message)
    
    @pytest.mark.asyncio
    async def test_send_to_extension_no_connection(self, server):
        """Test sending message when no extension connected"""
        message = {"type": "request", "action": "test"}
        
        result = await server.send_to_extension(message)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_to_extension_success(self, server, mock_websocket):
        """Test successful message sending to extension"""
        server.extension_connection = mock_websocket
        message = {"type": "request", "action": "test"}
        
        result = await server.send_to_extension(message)
        
        assert result is True
        mock_websocket.send.assert_called_once()
        
        # Verify message has timestamp added
        sent_message = json.loads(mock_websocket.send.call_args[0][0])
        assert "timestamp" in sent_message
        assert sent_message["type"] == "request"
        assert sent_message["action"] == "test"
    
    @pytest.mark.asyncio
    async def test_send_to_extension_error(self, server, mock_websocket):
        """Test error handling when sending to extension"""
        server.extension_connection = mock_websocket
        mock_websocket.send.side_effect = Exception("Send failed")
        
        message = {"type": "request", "action": "test"}
        result = await server.send_to_extension(message)
        
        assert result is False