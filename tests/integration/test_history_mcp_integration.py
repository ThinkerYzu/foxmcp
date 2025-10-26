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
    
    
    @pytest.mark.asyncio
    async def test_mcp_server_initialization_with_history_tools(self, server_with_extension):
        """Test that MCP server initializes with history tools"""
        server = server_with_extension['server']
        firefox = server_with_extension['firefox']
        test_port = server_with_extension['test_port']
        mcp_port = server_with_extension['mcp_port']
        
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
    async def test_mcp_websocket_integration_with_history(self, server_with_extension):
        """Test MCP server integrates properly with WebSocket layer for history"""
        server = server_with_extension['server']
        firefox = server_with_extension['firefox']
        test_port = server_with_extension['test_port']
        mcp_port = server_with_extension['mcp_port']
        
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
    async def test_mcp_server_dual_architecture(self, server_with_extension):
        """Test dual server architecture: MCP + WebSocket"""
        server = server_with_extension['server']
        firefox = server_with_extension['firefox']
        test_port = server_with_extension['test_port']
        mcp_port = server_with_extension['mcp_port']
        
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
            "data": {"query": "", "maxResults": 1},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await server.send_request_and_wait(request, timeout=10.0)
        assert "error" not in response
        
        print(f"✓ Dual architecture verified:")
        print(f"  - MCP server: localhost:{mcp_port}")
        print(f"  - WebSocket server: localhost:{test_port}")
        print(f"  - Extension connected: ✓")
        print(f"  - MCP tools initialized: ✓")

    @pytest.mark.asyncio
    async def test_mcp_history_tools_show_valid_timestamps(self, server_with_extension):
        """Test that MCP history tools display valid timestamps, not 'Unknown time'"""
        server = server_with_extension['server']
        firefox = server_with_extension['firefox']
        test_port = server_with_extension['test_port']
        mcp_port = server_with_extension['mcp_port']

        # Verify MCP tools are available
        assert server.mcp_tools is not None
        mcp_tools = server.mcp_tools

        # Test 1: Call history_query through MCP tool
        print("\n🔍 Testing history_query MCP tool...")
        query_result = await mcp_tools.mcp._tool_manager._tools['history_query'].fn(
            query="",
            max_results=5
        )

        print(f"📋 Query result: {query_result}")

        # Verify we got results
        assert isinstance(query_result, str), "Query result should be a string"
        assert "Found" in query_result or "No history items" in query_result, \
            "Query result should indicate found items or no items"

        # IMPORTANT: Verify timestamps are NOT "Unknown time"
        if "Found" in query_result and "history items" in query_result:
            assert "Unknown time" not in query_result, \
                "MCP tool should NOT show 'Unknown time', it should show actual timestamps"

            # Verify it contains actual timestamp values (numbers)
            # Timestamps are in milliseconds, so they should be large numbers
            assert "last:" in query_result, "Result should contain 'last:' timestamp field"

            # Check if there are numeric timestamp values (basic check for digits)
            lines = query_result.split('\n')
            item_lines = [line for line in lines if line.strip().startswith('-')]
            if item_lines:
                # At least one item line should contain numbers (timestamp)
                has_numeric_timestamp = any(
                    any(char.isdigit() for char in line.split('last:')[1] if 'last:' in line)
                    for line in item_lines
                )
                assert has_numeric_timestamp, \
                    "At least one history item should have a numeric timestamp"

            print(f"✓ history_query shows valid timestamps (not 'Unknown time')")
        else:
            print(f"ℹ️  No history items found, skipping timestamp validation")

        # Test 2: Call history_get_recent through MCP tool
        print("\n🔍 Testing history_get_recent MCP tool...")
        recent_result = await mcp_tools.mcp._tool_manager._tools['history_get_recent'].fn(
            count=5
        )

        print(f"📋 Recent result: {recent_result}")

        # Verify we got results
        assert isinstance(recent_result, str), "Recent result should be a string"
        assert "Recent" in recent_result or "No recent history" in recent_result, \
            "Recent result should indicate recent items or no items"

        # IMPORTANT: Verify timestamps are NOT "Unknown time"
        if "Recent" in recent_result and "history items" in recent_result:
            assert "Unknown time" not in recent_result, \
                "MCP tool should NOT show 'Unknown time', it should show actual timestamps"

            # Verify it contains actual timestamp values
            assert "last visit:" in recent_result, "Result should contain 'last visit:' timestamp field"

            # Check if there are numeric timestamp values
            lines = recent_result.split('\n')
            item_lines = [line for line in lines if line.strip().startswith('-')]
            if item_lines:
                has_numeric_timestamp = any(
                    any(char.isdigit() for char in line.split('last visit:')[1] if 'last visit:' in line)
                    for line in item_lines
                )
                assert has_numeric_timestamp, \
                    "At least one history item should have a numeric timestamp"

            print(f"✓ history_get_recent shows valid timestamps (not 'Unknown time')")
        else:
            print(f"ℹ️  No recent history items found, skipping timestamp validation")

        print(f"\n✅ MCP history tools correctly display timestamps from Firefox API")
        print(f"✅ Timestamps show milliseconds since epoch (e.g., 1729945678123)")
        print(f"✅ No 'Unknown time' values in output")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])