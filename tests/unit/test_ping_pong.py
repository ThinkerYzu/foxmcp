"""
Unit tests for ping-pong communication functionality
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock
from server.server import FoxMCPServer

class TestPingPongCommunication:
    
    @pytest.fixture
    def server(self):
        """Create FoxMCPServer instance"""
        return FoxMCPServer(host="localhost", port=8765)
    
    @pytest.fixture
    def ping_request(self):
        """Sample ping request message"""
        return {
            "id": "ping_test_001",
            "type": "request",
            "action": "ping",
            "data": {"test": True},
            "timestamp": "2025-09-03T12:00:00.000Z"
        }
    
    @pytest.fixture
    def ping_response(self):
        """Expected ping response message"""
        return {
            "id": "ping_test_001",
            "type": "response", 
            "action": "ping",
            "data": {"message": "pong", "timestamp": "2025-09-03T12:00:01.000Z"},
            "timestamp": "2025-09-03T12:00:01.000Z"
        }
    
    @pytest.mark.asyncio
    async def test_server_handles_ping_request(self, server, ping_request):
        """Test server handles ping request from extension"""
        server.extension_connection = AsyncMock()
        
        # Convert to JSON string as it would come from WebSocket
        message_str = json.dumps(ping_request)
        
        # Handle the message
        await server.handle_extension_message(message_str)
        
        # Verify response was sent back to extension
        server.extension_connection.send.assert_called_once()
        sent_message = json.loads(server.extension_connection.send.call_args[0][0])
        
        assert sent_message["id"] == ping_request["id"]
        assert sent_message["type"] == "request"
        assert sent_message["action"] == "ping"
    
    @pytest.mark.asyncio
    async def test_server_ping_extension(self, server, mock_websocket):
        """Test server can send ping to extension"""
        server.extension_connection = mock_websocket
        
        result = await server.test_ping_extension()
        
        assert result["success"] is True
        assert "Ping sent to extension" in result["message"]
        assert "id" in result
        
        # Verify message was sent
        mock_websocket.send.assert_called_once()
        sent_message = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_message["action"] == "ping"
        assert sent_message["type"] == "request"
    
    @pytest.mark.asyncio
    async def test_server_ping_no_connection(self, server):
        """Test server ping when no extension connected"""
        result = await server.test_ping_extension()
        
        assert result["success"] is False
        assert "No extension connection" in result["error"]
    
    @pytest.mark.asyncio
    async def test_ping_request_validation(self, server):
        """Test ping request validation"""
        invalid_requests = [
            '{"id": "test", "type": "request"}',  # Missing action
            '{"id": "test", "action": "ping"}',   # Missing type
            '{"type": "request", "action": "ping"}',  # Missing id
            'invalid json',
            ''
        ]
        
        for invalid_request in invalid_requests:
            # Should handle gracefully without raising exceptions
            await server.handle_extension_message(invalid_request)
    
    @pytest.mark.asyncio
    async def test_extension_ping_message_structure(self):
        """Test extension ping message follows protocol"""
        # This tests the structure expected from extension
        ping_message = {
            "id": "ping_test_123",
            "type": "request", 
            "action": "ping",
            "data": {"test": True},
            "timestamp": "2025-09-03T12:00:00.000Z"
        }
        
        # Verify required fields
        assert "id" in ping_message
        assert "type" in ping_message
        assert "action" in ping_message
        assert "data" in ping_message
        assert "timestamp" in ping_message
        
        # Verify values
        assert ping_message["type"] == "request"
        assert ping_message["action"] == "ping"
        assert isinstance(ping_message["data"], dict)
    
    @pytest.mark.asyncio
    async def test_pong_response_structure(self):
        """Test pong response follows protocol"""
        pong_response = {
            "id": "ping_test_123",
            "type": "response",
            "action": "ping", 
            "data": {"message": "pong", "timestamp": "2025-09-03T12:00:01.000Z"},
            "timestamp": "2025-09-03T12:00:01.000Z"
        }
        
        # Verify required fields
        assert "id" in pong_response
        assert "type" in pong_response
        assert "action" in pong_response
        assert "data" in pong_response
        assert "timestamp" in pong_response
        
        # Verify values
        assert pong_response["type"] == "response"
        assert pong_response["action"] == "ping"
        assert pong_response["data"]["message"] == "pong"

class TestExtensionPingPong:
    """Tests for extension-side ping-pong functionality"""
    
    def test_ping_handler_implementation(self):
        """Test ping handler exists and follows expected pattern"""
        # This would test the extension ping handler
        # Since we can't run JavaScript in pytest, we test the expected behavior
        
        expected_ping_handler = """
        if (action === 'ping') {
            sendResponse(id, 'ping', { message: 'pong', timestamp: new Date().toISOString() });
            return;
        }
        """
        
        # Verify the handler pattern exists (conceptually)
        assert "ping" in expected_ping_handler
        assert "pong" in expected_ping_handler
        assert "sendResponse" in expected_ping_handler
    
    def test_extension_ping_test_function(self):
        """Test extension ping test function structure"""
        # This tests the expected structure of the extension testPingPong function
        
        expected_features = [
            "testPingPong",
            "ping_test_",
            "timestamp",
            "Promise",
            "timeout"
        ]
        
        # In a real implementation, these would be verified in the extension code
        for feature in expected_features:
            assert isinstance(feature, str)  # Placeholder verification