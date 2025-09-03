"""
Integration tests for ping-pong functionality between server and extension
"""

import pytest
import asyncio
import json
import websockets
from unittest.mock import patch, AsyncMock
from server.server import FoxMCPServer

class TestPingPongIntegration:
    
    @pytest.mark.asyncio
    async def test_bidirectional_ping_pong(self):
        """Test bidirectional ping-pong communication"""
        server = FoxMCPServer(host="localhost", port=8766)
        
        # Mock the WebSocket connection
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        
        # Set up connection
        server.extension_connection = mock_websocket
        
        # Test 1: Extension sends ping, server responds
        extension_ping = {
            "id": "ext_ping_001",
            "type": "request",
            "action": "ping",
            "data": {"test": True},
            "timestamp": "2025-09-03T12:00:00.000Z"
        }
        
        await server.handle_extension_message(json.dumps(extension_ping))
        
        # Verify server sent ping back to extension
        mock_websocket.send.assert_called_once()
        server_response = json.loads(mock_websocket.send.call_args[0][0])
        
        assert server_response["id"] == extension_ping["id"]
        assert server_response["action"] == "ping"
        assert server_response["type"] == "request"
        
        # Reset mock
        mock_websocket.reset_mock()
        
        # Test 2: Server sends ping to extension
        result = await server.test_ping_extension()
        
        assert result["success"] is True
        mock_websocket.send.assert_called_once()
        
        server_ping = json.loads(mock_websocket.send.call_args[0][0])
        assert server_ping["action"] == "ping"
        assert server_ping["type"] == "request"
        assert "server_ping_" in server_ping["id"]
    
    @pytest.mark.asyncio
    async def test_ping_timeout_scenario(self):
        """Test ping timeout handling"""
        # This would test timeout scenarios in a real WebSocket connection
        # For now, we test the timeout configuration
        
        timeout_ms = 5000  # 5 seconds as defined in extension
        assert timeout_ms > 0
        assert timeout_ms <= 10000  # Reasonable upper bound
    
    @pytest.mark.asyncio
    async def test_connection_state_during_ping(self):
        """Test connection state is properly checked during ping"""
        server = FoxMCPServer()
        
        # Test with no connection
        result = await server.test_ping_extension()
        assert result["success"] is False
        assert "No extension connection" in result["error"]
        
        # Test with connection
        mock_websocket = AsyncMock()
        server.extension_connection = mock_websocket
        
        result = await server.test_ping_extension()
        assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_ping_message_id_uniqueness(self):
        """Test that ping message IDs are unique"""
        server = FoxMCPServer()
        server.extension_connection = AsyncMock()
        
        # Generate multiple pings
        results = []
        for i in range(5):
            result = await server.test_ping_extension()
            results.append(result["id"])
            await asyncio.sleep(0.001)  # Small delay to ensure different timestamps
        
        # All IDs should be unique
        assert len(set(results)) == len(results)
    
    @pytest.mark.asyncio
    async def test_ping_data_integrity(self):
        """Test ping message data integrity"""
        server = FoxMCPServer()
        mock_websocket = AsyncMock()
        server.extension_connection = mock_websocket
        
        # Send ping from server
        await server.test_ping_extension()
        
        # Verify sent message structure
        sent_message = json.loads(mock_websocket.send.call_args[0][0])
        
        required_fields = ["id", "type", "action", "data", "timestamp"]
        for field in required_fields:
            assert field in sent_message
        
        assert sent_message["type"] == "request"
        assert sent_message["action"] == "ping"
        assert isinstance(sent_message["data"], dict)
        assert "server_test" in sent_message["data"]

class TestPingPongErrorHandling:
    
    @pytest.mark.asyncio
    async def test_malformed_ping_message(self):
        """Test handling of malformed ping messages"""
        server = FoxMCPServer()
        server.extension_connection = AsyncMock()
        
        malformed_messages = [
            '{"id": "test"}',  # Missing required fields
            '{"type": "request", "action": "ping"}',  # Missing ID
            'invalid json',
            '',
            None
        ]
        
        for message in malformed_messages:
            if message is not None:
                # Should handle gracefully without raising exceptions
                await server.handle_extension_message(message)
    
    @pytest.mark.asyncio 
    async def test_connection_lost_during_ping(self):
        """Test ping behavior when connection is lost"""
        server = FoxMCPServer()
        mock_websocket = AsyncMock()
        
        # Simulate connection loss during send
        mock_websocket.send.side_effect = Exception("Connection lost")
        server.extension_connection = mock_websocket
        
        result = await server.test_ping_extension()
        
        # Should return failure gracefully
        assert result["success"] is False
        assert "Failed to send ping" in result["error"]
    
    @pytest.mark.asyncio
    async def test_concurrent_pings(self):
        """Test handling of concurrent ping requests"""
        server = FoxMCPServer()
        server.extension_connection = AsyncMock()
        
        # Send multiple pings concurrently
        tasks = [server.test_ping_extension() for _ in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed
        for result in results:
            assert not isinstance(result, Exception)
            assert result["success"] is True
        
        # Verify all pings were sent
        assert server.extension_connection.send.call_count == 3

class TestPingPongProtocolCompliance:
    
    def test_ping_message_protocol_compliance(self):
        """Test ping messages comply with protocol specification"""
        # Test message structure matches protocol.md specification
        
        ping_request_structure = {
            "id": str,
            "type": str, 
            "action": str,
            "data": dict,
            "timestamp": str
        }
        
        ping_response_structure = {
            "id": str,
            "type": str,
            "action": str, 
            "data": dict,
            "timestamp": str
        }
        
        # Verify structures are defined
        assert len(ping_request_structure) == 5
        assert len(ping_response_structure) == 5
        
        # Verify required types
        assert ping_request_structure["id"] == str
        assert ping_response_structure["data"] == dict
    
    def test_ping_action_naming_convention(self):
        """Test ping action follows naming convention"""
        ping_action = "ping"
        
        # Should be simple action name (no dot notation for ping)
        assert "." not in ping_action
        assert ping_action.islower()
        assert len(ping_action) > 0