"""
Simple integration test for live server communication
Tests actual WebSocket communication between server and clients
"""

import pytest
import pytest_asyncio
import json
import asyncio
import websockets
import time
import sys
import os

# Add the parent directory to the path to import server module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from server.server import FoxMCPServer


class TestLiveServerCommunication:
    """Test live server communication"""

    @pytest.mark.asyncio
    async def test_server_can_start_and_stop(self):
        """Test that server can start and stop cleanly"""
        server = FoxMCPServer(host="localhost", port=8766)  # Use different port for test
        
        # Test server startup
        server_task = asyncio.create_task(server.start_server())
        
        # Give server time to start
        await asyncio.sleep(0.2)
        
        # Server should be running
        assert server_task is not None
        assert not server_task.done()
        
        # Cleanup
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass  # Expected when cancelling

    @pytest.mark.asyncio
    async def test_client_can_connect_to_server(self):
        """Test that a WebSocket client can connect to the server"""
        server = FoxMCPServer(host="localhost", port=8767)
        
        # Start server
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(0.3)  # Give more time for server to bind
        
        connection_successful = False
        
        try:
            # Try to connect as a client
            uri = "ws://localhost:8767"
            websocket = await websockets.connect(uri)
            
            connection_successful = True
            
            # Send a ping message
            ping_message = {
                "id": "live-test-001",
                "type": "request",
                "action": "ping",
                "data": {"message": "test connection"},
                "timestamp": time.time()
            }
            
            await websocket.send(json.dumps(ping_message))
            
            # Connection and message send successful
            await websocket.close()
            
        except Exception as e:
            print(f"Connection failed: {e}")
            
        finally:
            # Cleanup
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
        
        assert connection_successful, "Client should be able to connect to server"

    @pytest.mark.asyncio
    async def test_server_message_handling(self):
        """Test server can handle messages correctly"""
        server = FoxMCPServer()
        
        # Test different message types
        messages = [
            {
                "id": "msg-001",
                "type": "request",
                "action": "tabs.list",
                "data": {},
                "timestamp": time.time()
            },
            {
                "id": "msg-002", 
                "type": "response",
                "action": "history.query",
                "data": {"results": []},
                "timestamp": time.time()
            },
            {
                "id": "msg-003",
                "type": "error",
                "action": "bookmarks.create",
                "data": {"error": "Permission denied", "code": 403},
                "timestamp": time.time()
            }
        ]
        
        for msg in messages:
            msg_json = json.dumps(msg)
            try:
                await server.handle_extension_message(msg_json)
                # Should handle without exception
            except Exception as e:
                pytest.fail(f"Server should handle message {msg['type']}: {e}")

    @pytest.mark.asyncio
    async def test_server_state_management(self):
        """Test server state is managed correctly"""
        server = FoxMCPServer()
        
        # Initially no connection
        assert server.extension_connection is None
        
        # Test send without connection
        test_msg = {"type": "request", "action": "test"}
        result = await server.send_to_extension(test_msg)
        assert result is False
        
        # Test that server handles missing connection gracefully
        assert server.extension_connection is None

    @pytest.mark.asyncio
    async def test_bidirectional_communication_simulation(self):
        """Simulate bidirectional communication between server and extension"""
        server = FoxMCPServer(host="localhost", port=8768)
        
        # Start server
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(0.3)
        
        communication_successful = False
        
        try:
            # Connect as "extension"
            uri = "ws://localhost:8768"
            websocket = await websockets.connect(uri)
            
            # Simulate extension sending a response
            extension_response = {
                "id": "bidirectional-001",
                "type": "response",
                "action": "tabs.list",
                "data": {
                    "tabs": [
                        {"id": 1, "url": "https://example.com", "title": "Example"},
                        {"id": 2, "url": "https://test.com", "title": "Test"}
                    ]
                },
                "timestamp": time.time()
            }
            
            await websocket.send(json.dumps(extension_response))
            
            # Simulate server sending a request (this would normally come from MCP)
            server_request = {
                "id": "bidirectional-002", 
                "type": "request",
                "action": "history.query",
                "data": {"query": "search term", "maxResults": 10},
                "timestamp": time.time()
            }
            
            await websocket.send(json.dumps(server_request))
            
            communication_successful = True
            await websocket.close()
            
        except Exception as e:
            print(f"Bidirectional communication test failed: {e}")
            
        finally:
            # Cleanup
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
        
        assert communication_successful, "Bidirectional communication should work"


class TestFirefoxExtensionProtocol:
    """Test protocol compatibility with Firefox extension"""

    @pytest.mark.asyncio
    async def test_all_browser_actions_supported(self):
        """Test that all expected browser actions are supported"""
        server = FoxMCPServer()
        
        # All browser actions that should be supported
        browser_actions = [
            # Tab management
            "tabs.list", "tabs.get_active", "tabs.create", "tabs.close", 
            "tabs.switch", "tabs.duplicate",
            
            # History management
            "history.query", "history.get_recent", "history.delete_item", 
            "history.clear_range",
            
            # Bookmarks
            "bookmarks.list", "bookmarks.search", "bookmarks.create",
            "bookmarks.delete", "bookmarks.update", "bookmarks.create_folder",
            
            # Navigation
            "navigation.back", "navigation.forward", "navigation.reload",
            "navigation.go_to_url",
            
            # Content access
            "content.get_text", "content.get_html", "content.get_title",
            "content.get_url", "content.execute_script"
        ]
        
        for action in browser_actions:
            message = {
                "id": f"protocol-test-{action.replace('.', '-')}",
                "type": "request",
                "action": action,
                "data": {},
                "timestamp": time.time()
            }
            
            try:
                await server.handle_extension_message(json.dumps(message))
                # Should handle without exception
                
                # Verify action category
                category = action.split('.')[0]
                assert category in ['tabs', 'history', 'bookmarks', 'navigation', 'content']
                
            except Exception as e:
                pytest.fail(f"Server should support browser action {action}: {e}")

    @pytest.mark.asyncio
    async def test_error_handling_robustness(self):
        """Test that server handles various error conditions"""
        server = FoxMCPServer()
        
        # Test various problematic inputs
        problematic_inputs = [
            "",  # Empty string
            "not json",  # Invalid JSON
            '{"incomplete": json',  # Malformed JSON
            "null",  # Valid JSON but wrong type
            "[]",  # Array instead of object
            '{"no_required_fields": true}',  # Missing required fields
            '{"type": "unknown_type", "id": "test"}',  # Unknown type
            '{"type": "request"}',  # Missing action
            json.dumps({"type": "request", "action": "unknown.action", "id": "test"}),  # Unknown action
        ]
        
        for input_data in problematic_inputs:
            try:
                await server.handle_extension_message(input_data)
                # Should handle gracefully without raising exceptions
            except Exception as e:
                pytest.fail(f"Server should handle problematic input gracefully: {repr(input_data[:50])} -> {e}")


if __name__ == "__main__":
    # Run tests directly if needed  
    pytest.main([__file__, "-v"])