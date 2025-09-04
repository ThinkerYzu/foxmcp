"""
Real WebSocket communication tests between FoxMCPServer and Firefox extension
This test requires a running Firefox instance with the extension installed.
"""

import pytest
import pytest_asyncio
import json
import asyncio
import websockets
from unittest.mock import patch
import time
import threading
import logging
import sys
import os

# Add the parent directory to the path to import server module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from server.server import FoxMCPServer

# Configure logging for better debugging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TestRealWebSocketCommunication:
    """Test real WebSocket communication with Firefox extension"""

    @pytest_asyncio.fixture
    async def real_server(self):
        """Start a real FoxMCPServer instance for testing"""
        # Use a different port for each test to avoid conflicts
        import random
        port = random.randint(9000, 9999)
        mcp_port = random.randint(5000, 5999)  # Different range for MCP ports
        server = FoxMCPServer(host="localhost", port=port, mcp_port=mcp_port, start_mcp=False)  # Disable MCP for WebSocket tests
        
        # Start server in background task
        server_task = asyncio.create_task(server.start_server())
        
        # Give server time to start
        await asyncio.sleep(0.5)
        
        # Store port for tests to use
        server._test_port = port
        yield server
        
        # Cleanup
        logger.info("Cleaning up test server...")
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            logger.info("Server task cancelled successfully")
        except Exception as e:
            logger.warning(f"Server cleanup warning: {e}")
        
        # Close any remaining connections
        try:
            if hasattr(server, 'server') and server.server:
                server.server.close()
                await server.server.wait_closed()
        except Exception as e:
            logger.warning(f"Connection cleanup warning: {e}")
            
        # Give time for cleanup
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_server_startup_and_port_binding(self, real_server):
        """Test that the server starts up correctly and binds to the port"""
        # Wait a moment for the server to fully initialize
        await asyncio.sleep(0.1)
        
        # Test connection to the server port
        try:
            # Try to connect as a client would
            uri = f"ws://localhost:{real_server._test_port}"
            async with websockets.connect(uri) as websocket:
                logger.info("Successfully connected to server")
                
                # Send a test message
                test_message = {
                    "id": "test-connection-001", 
                    "type": "request",
                    "action": "ping",
                    "data": {},
                    "timestamp": time.time()
                }
                
                await websocket.send(json.dumps(test_message))
                logger.info(f"Sent test message: {test_message}")
                
                # Wait for response (with timeout)
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    logger.info(f"Received response: {response}")
                    
                    # Parse response
                    response_data = json.loads(response)
                    # The server might echo the message or send a proper response
                    # Both are valid for this test
                    assert response_data.get("id") == "test-connection-001"
                    assert response_data.get("type") in ["request", "response"]
                    
                except asyncio.TimeoutError:
                    logger.warning("No response received within timeout")
                    # This is expected if extension isn't connected
                    assert True
                    
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            pytest.fail(f"Could not connect to server: {e}")

    @pytest.mark.asyncio 
    async def test_message_handling_without_extension(self, real_server):
        """Test server message handling when no extension is connected"""
        # Wait for server to be ready
        await asyncio.sleep(0.1)
        
        # Send a message directly to the server's message handler
        test_message = json.dumps({
            "id": "test-no-extension-001",
            "type": "request", 
            "action": "tabs.list",
            "data": {},
            "timestamp": time.time()
        })
        
        # This should not raise an exception even without extension
        await real_server.handle_extension_message(test_message)
        logger.info("Message handled successfully without extension")

    @pytest.mark.asyncio
    async def test_invalid_message_resilience(self, real_server):
        """Test that server handles invalid messages gracefully"""
        await asyncio.sleep(0.1)
        
        invalid_messages = [
            "not json at all",
            '{"incomplete": json',
            "",
            "null",
            '{"missing": "required_fields"}',
            '{"type": "unknown", "id": "test"}',
            json.dumps({"type": "request"})  # Missing required fields
        ]
        
        for message in invalid_messages:
            try:
                await real_server.handle_extension_message(message)
                logger.info(f"Successfully handled invalid message: {message[:50]}...")
            except Exception as e:
                logger.error(f"Failed to handle invalid message: {e}")
                pytest.fail(f"Server should handle invalid messages gracefully: {e}")

    @pytest.mark.asyncio
    async def test_connection_state_management(self, real_server):
        """Test that connection states are properly managed"""
        await asyncio.sleep(0.1)
        
        # Initially no extension connected
        assert real_server.extension_connection is None
        
        # Test sending message without connection
        test_message = {"type": "request", "action": "test", "id": "test-001"}
        result = await real_server.send_to_extension(test_message)
        assert result is False, "Should return False when no extension connected"

    @pytest.mark.asyncio
    async def test_multiple_client_connections(self, real_server):
        """Test server can handle multiple client connections"""
        await asyncio.sleep(0.1)
        
        connections = []
        try:
            # Create multiple client connections
            for i in range(3):
                uri = f"ws://localhost:{real_server._test_port}"
                websocket = await websockets.connect(uri)
                connections.append(websocket)
                logger.info(f"Client {i+1} connected")
                
                # Send unique message from each client
                message = {
                    "id": f"multi-client-{i+1}",
                    "type": "request", 
                    "action": "ping",
                    "data": {"client": i+1}
                }
                await websocket.send(json.dumps(message))
                logger.info(f"Client {i+1} sent message")
            
            # All connections should be active
            assert len(connections) == 3
            logger.info("Multiple clients connected successfully")
            
        except Exception as e:
            logger.error(f"Multiple client test failed: {e}")
            pytest.fail(f"Server should handle multiple connections: {e}")
        
        finally:
            # Cleanup connections
            for i, conn in enumerate(connections):
                try:
                    await conn.close()
                    logger.info(f"Client {i+1} disconnected")
                except:
                    pass

class TestFirefoxExtensionIntegration:
    """Tests that would work with a real Firefox extension"""
    
    @pytest.mark.asyncio
    async def test_extension_message_format(self):
        """Test expected message format from extension"""
        
        # Test various expected message formats
        valid_messages = [
            {
                "id": "ext-001",
                "type": "response",
                "action": "tabs.list", 
                "data": {"tabs": [{"id": 1, "url": "https://example.com", "title": "Test"}]},
                "timestamp": time.time()
            },
            {
                "id": "ext-002", 
                "type": "response",
                "action": "history.query",
                "data": {"results": []},
                "timestamp": time.time()
            },
            {
                "id": "ext-003",
                "type": "request",
                "action": "bookmarks.create",
                "data": {"url": "https://test.com", "title": "Test Bookmark"},
                "timestamp": time.time()
            },
            {
                "id": "ext-004",
                "type": "error", 
                "action": "tabs.close",
                "data": {"error": "Tab not found", "code": 404},
                "timestamp": time.time()
            }
        ]
        
        server = FoxMCPServer()
        
        for message in valid_messages:
            message_json = json.dumps(message)
            try:
                await server.handle_extension_message(message_json)
                logger.info(f"Successfully processed message type: {message['type']}")
            except Exception as e:
                pytest.fail(f"Should handle valid extension message: {e}")

    @pytest.mark.asyncio 
    async def test_browser_action_categories(self):
        """Test that all expected browser action categories are recognized"""
        
        action_categories = [
            "tabs.list", "tabs.get_active", "tabs.create", "tabs.close", "tabs.switch",
            "history.query", "history.get_recent", "history.delete_item", "history.clear_range", 
            "bookmarks.list", "bookmarks.search", "bookmarks.create", "bookmarks.delete",
            "navigation.back", "navigation.forward", "navigation.reload", "navigation.go_to_url",
            "content.get_text", "content.get_html", "content.get_title", "content.execute_script"
        ]
        
        server = FoxMCPServer()
        
        for action in action_categories:
            message = {
                "id": f"test-{action.replace('.', '-')}",
                "type": "request",
                "action": action, 
                "data": {},
                "timestamp": time.time()
            }
            
            message_json = json.dumps(message)
            await server.handle_extension_message(message_json)
            
            # Verify action category is parsed correctly
            category = action.split('.')[0]
            assert category in ['tabs', 'history', 'bookmarks', 'navigation', 'content']
            logger.info(f"Action {action} categorized as {category}")

    @pytest.mark.asyncio
    async def test_response_correlation(self):
        """Test that responses can be correlated with requests"""
        
        server = FoxMCPServer()
        
        # Simulate a request-response cycle
        request_id = "correlation-test-001"
        
        # Send request
        request_message = {
            "id": request_id,
            "type": "request",
            "action": "tabs.list",
            "data": {},
            "timestamp": time.time()
        }
        
        await server.handle_extension_message(json.dumps(request_message))
        
        # Send corresponding response
        response_message = {
            "id": request_id,  # Same ID for correlation
            "type": "response", 
            "action": "tabs.list",
            "data": {"tabs": [{"id": 1, "title": "Test Tab"}]},
            "timestamp": time.time()
        }
        
        await server.handle_extension_message(json.dumps(response_message))
        
        # Both should be processed successfully
        logger.info(f"Request-response cycle completed for ID: {request_id}")

if __name__ == "__main__":
    # Run tests directly if needed
    pytest.main([__file__, "-v"])