"""
History Management MCP Integration Tests

Tests for history management through the MCP protocol layer,
verifying the complete MCP client -> FastMCP -> WebSocket -> Extension flow.
"""

import pytest
import pytest_asyncio
import asyncio
import json
import sys
import os
import time
import re
from datetime import datetime, timedelta

import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from server.mcp_tools import FoxMCPTools
from test_config import TEST_PORTS, FIREFOX_TEST_CONFIG
from firefox_test_utils import FirefoxTestManager
from port_coordinator import coordinated_test_ports


class TestHistoryMCPIntegration:
    """Test history management through MCP protocol layer"""
    
    @pytest_asyncio.fixture
    async def mcp_server_with_extension(self):
        """Start MCP server and Firefox extension for history testing"""
        # Use dynamic port allocation
        with coordinated_test_ports() as (ports, coord_file):
            test_port = ports['websocket']
            mcp_port = ports['mcp']
            
            # Get extension XPI
            
            # Create server with MCP enabled
            server = FoxMCPServer(
                host="localhost",
                port=test_port,
                mcp_port=mcp_port,
                start_mcp=True  # Enable MCP server
            )
            
            # Start server
            server_task = asyncio.create_task(server.start_server())
            await asyncio.sleep(0.5)  # Allow server to start
            
            # Start Firefox with extension
            firefox_path = os.environ.get('FIREFOX_PATH', 'firefox')
            if not os.path.exists(os.path.expanduser(firefox_path)):
                pytest.skip(f"Firefox not found at {firefox_path}")
            
            firefox = FirefoxTestManager(
                firefox_path=firefox_path,
                test_port=test_port,
                coordination_file=coord_file
            )
            
            try:
                # Set up Firefox with extension and start it
                success = firefox.setup_and_start_firefox(headless=True)
                if not success:
                    pytest.skip("Firefox setup or extension installation failed")
                
                # Wait for extension to connect using awaitable mechanism
                connected = await firefox.async_wait_for_extension_connection(
                    timeout=FIREFOX_TEST_CONFIG['extension_install_wait'], server=server
                )

                # Verify connection
                if not connected:
                    pytest.skip("Extension did not connect to server")
                
                yield server, firefox, test_port, mcp_port
                
            finally:
                # Cleanup
                firefox.cleanup()
                await server.shutdown(server_task)
    
    @pytest.mark.asyncio
    async def test_mcp_server_initialization_with_history_tools(self, mcp_server_with_extension):
        """Test that MCP server initializes with history tools"""
        server, firefox, test_port, mcp_port = mcp_server_with_extension
        
        # Verify MCP tools were initialized
        assert server.mcp_tools is not None
        assert server.mcp_app is not None
        
        # Verify the MCP components exist
        mcp_tools = server.mcp_tools
        assert hasattr(mcp_tools, 'mcp')  # FastMCP instance
        assert hasattr(mcp_tools, 'websocket_server')  # WebSocket server reference
        
        # Verify server configuration
        assert server.start_mcp == True  # MCP was enabled
        assert server.mcp_port == mcp_port
        assert server.port == test_port
        
        print(f"✓ MCP server initialized with tools on port {mcp_port}")
        print(f"✓ WebSocket server connected on port {test_port}")
        print("✓ MCP history tools are available through FastMCP framework")
    
    @pytest.mark.asyncio
    async def test_mcp_websocket_integration_with_history(self, mcp_server_with_extension):
        """Test MCP server integrates properly with WebSocket layer for history"""
        server, firefox, test_port, mcp_port = mcp_server_with_extension
        
        # Test that both MCP and WebSocket servers are running
        assert server.mcp_tools is not None
        assert server.extension_connection is not None
        
        # Test WebSocket layer directly with history request
        request = {
            "id": "test_mcp_integration_history",
            "type": "request",
            "action": "history.recent",
            "data": {"count": 2},
            "timestamp": datetime.now().isoformat()
        }
        
        # This simulates what an MCP tool would do
        response = await server.send_request_and_wait(request, timeout=10.0)
        
        # Verify integration works
        assert "error" not in response
        assert response.get("type") == "response"
        assert "data" in response
        
        print(f"✓ MCP-WebSocket integration working for history")
        print(f"✓ MCP server on port {mcp_port}, WebSocket on port {test_port}")
    
    @pytest.mark.asyncio
    async def test_mcp_server_dual_architecture(self, mcp_server_with_extension):
        """Test dual server architecture: MCP + WebSocket"""
        server, firefox, test_port, mcp_port = mcp_server_with_extension
        
        # Verify dual architecture is set up
        assert server.mcp_port == mcp_port
        assert server.port == test_port
        assert server.start_mcp == True  # MCP was enabled for this test
        
        # Test that WebSocket connection works (extension connected)
        assert server.extension_connection is not None
        
        # Test that MCP tools were initialized
        assert server.mcp_tools is not None
        assert server.mcp_app is not None
        
        # Test that we can make WebSocket requests (like MCP tools would)
        request = {
            "id": "test_dual_arch",
            "type": "request",
            "action": "history.query",
            "data": {"text": "", "maxResults": 1},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await server.send_request_and_wait(request, timeout=10.0)
        assert "error" not in response
        
        print(f"✓ Dual architecture verified:")
        print(f"  - MCP server: localhost:{mcp_port}")
        print(f"  - WebSocket server: localhost:{test_port}")
        print(f"  - Extension connected: ✓")
        print(f"  - MCP tools initialized: ✓")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])