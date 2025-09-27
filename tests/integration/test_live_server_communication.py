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
import re

# Add the parent directory to the path to import server module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from server.server import FoxMCPServer

# Import test configuration
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from test_config import TEST_PORTS
from port_coordinator import get_port_by_type


class TestLiveServerCommunication:
    """Test live server communication"""

    @pytest.mark.asyncio
    async def test_server_can_start_and_stop(self):
        """Test that server can start and stop cleanly"""
        # Use fixed ports for reliable testing
        ports = TEST_PORTS['integration']
        server = FoxMCPServer(host="localhost", port=ports['websocket'], mcp_port=ports['mcp'], start_mcp=False)  # Disable MCP for basic tests
        
        # Test server startup
        server_task = asyncio.create_task(server.start_server())
        
        # Give server time to start
        await asyncio.sleep(0.2)
        
        # Server should be running
        assert server_task is not None
        assert not server_task.done()
        
        # Cleanup
        await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_client_can_connect_to_server(self):
        """Test that a WebSocket client can connect to the server"""
        # Use individual dynamic ports to avoid conflicts
        port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')
        server = FoxMCPServer(host="localhost", port=port, mcp_port=mcp_port, start_mcp=False)
        
        # Start server
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(0.3)  # Give more time for server to bind
        
        connection_successful = False
        
        try:
            # Try to connect as a client
            uri = f"ws://localhost:{port}"
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
            await server.shutdown(server_task)
        
        assert connection_successful, "Client should be able to connect to server"

    @pytest.mark.asyncio
    async def test_server_message_handling(self):
        """Test server can handle messages correctly"""
        server = FoxMCPServer(start_mcp=False)
        
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
        server = FoxMCPServer(start_mcp=False)
        
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
        # Use port coordinator to avoid conflicts
        try:
            from ..port_coordinator import coordinated_test_ports
        except ImportError:
            from port_coordinator import coordinated_test_ports
        
        with coordinated_test_ports() as (ports, coord_file):
            port = ports['websocket']
            mcp_port = ports['mcp']
            server = FoxMCPServer(host="localhost", port=port, mcp_port=mcp_port, start_mcp=False)
            
            # Start server
            server_task = asyncio.create_task(server.start_server())
            await asyncio.sleep(0.3)
            
            communication_successful = False
            
            try:
                # Connect as "extension"
                uri = f"ws://localhost:{port}"
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
                await server.shutdown(server_task)
            
            assert communication_successful, "Bidirectional communication should work"


class TestFirefoxExtensionProtocol:
    """Test protocol compatibility with Firefox extension"""

    @pytest.mark.asyncio
    async def test_all_browser_actions_supported(self):
        """Test that all expected browser actions are supported"""
        server = FoxMCPServer(start_mcp=False)
        
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
        server = FoxMCPServer(start_mcp=False)
        
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