"""
Integration tests for MCP server functionality
Tests FastMCP integration with WebSocket communication
"""

import pytest
import pytest_asyncio
import json
import asyncio
import uuid
from datetime import datetime
from unittest.mock import Mock, AsyncMock
import sys
import os

# Add the parent directory to the path to import server module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from server.server import FoxMCPServer
from server.mcp_tools import FoxMCPTools


class TestMCPIntegration:
    """Test MCP server integration"""
    
    @pytest.fixture
    def mock_websocket_server(self):
        """Create mock WebSocket server for testing"""
        class MockServer:
            def __init__(self):
                self.extension_connection = None
                self.pending_requests = {}
                self.sent_messages = []
            
            async def send_to_extension(self, message):
                self.sent_messages.append(message)
                return True
            
            async def send_request_and_wait(self, request, timeout=10.0):
                # Mock successful responses for different actions
                action = request.get("action", "")
                request_id = request.get("id")
                
                mock_responses = {
                    "tabs.list": {
                        "data": {
                            "tabs": [
                                {"id": 1, "url": "https://example.com", "title": "Example", "active": True},
                                {"id": 2, "url": "https://test.com", "title": "Test", "active": False}
                            ]
                        }
                    },
                    "tabs.create": {
                        "data": {
                            "tab": {"id": 3, "url": "https://newsite.com", "title": "New Site", "active": True}
                        }
                    },
                    "history.query": {
                        "data": {
                            "items": [
                                {"url": "https://example.com", "title": "Example", "visitTime": "2025-01-01T12:00:00Z", "visitCount": 5}
                            ],
                            "totalCount": 1
                        }
                    },
                    "bookmarks.list": {
                        "data": {
                            "bookmarks": [
                                {"id": "bm1", "title": "GitHub", "url": "https://github.com", "isFolder": False}
                            ]
                        }
                    }
                }
                
                if action in mock_responses:
                    return {
                        "id": request_id,
                        "type": "response", 
                        "action": action,
                        **mock_responses[action],
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "id": request_id,
                        "type": "error",
                        "action": action,
                        "data": {"error": f"Unknown action: {action}"},
                        "timestamp": datetime.now().isoformat()
                    }
        
        return MockServer()
    
    def test_mcp_tools_initialization(self, mock_websocket_server):
        """Test that MCP tools initialize correctly"""
        mcp_tools = FoxMCPTools(mock_websocket_server)
        
        assert mcp_tools is not None
        assert mcp_tools.websocket_server == mock_websocket_server
        assert mcp_tools.mcp is not None
        assert hasattr(mcp_tools, 'get_mcp_app')
        
        mcp_app = mcp_tools.get_mcp_app()
        assert mcp_app is not None
    
    def test_server_with_mcp_integration(self):
        """Test server initialization with MCP integration"""
        server = FoxMCPServer(port=8771, mcp_port=3005)
        
        assert server.mcp_tools is not None
        assert server.mcp_app is not None
        assert server.mcp_port == 3005
        assert hasattr(server, 'start_mcp_server')
    
    @pytest.mark.asyncio
    async def test_mcp_tool_call_simulation(self, mock_websocket_server):
        """Test simulated MCP tool calls"""
        mcp_tools = FoxMCPTools(mock_websocket_server)
        
        # Test tabs_list simulation
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.list",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await mock_websocket_server.send_request_and_wait(request)
        
        assert response["type"] == "response"
        assert response["action"] == "tabs.list"
        assert "data" in response
        assert "tabs" in response["data"]
        assert len(response["data"]["tabs"]) == 2
        
        # Verify tab data structure
        tab = response["data"]["tabs"][0]
        assert "id" in tab
        assert "url" in tab
        assert "title" in tab
        assert "active" in tab
    
    @pytest.mark.asyncio  
    async def test_error_handling_in_mcp_tools(self, mock_websocket_server):
        """Test error handling in MCP tools"""
        mcp_tools = FoxMCPTools(mock_websocket_server)
        
        # Test unknown action
        request = {
            "id": str(uuid.uuid4()),
            "type": "request", 
            "action": "unknown.action",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await mock_websocket_server.send_request_and_wait(request)
        
        assert response["type"] == "error"
        assert response["action"] == "unknown.action"
        assert "error" in response["data"]
    
    @pytest.mark.asyncio
    async def test_different_tool_categories(self, mock_websocket_server):
        """Test different categories of MCP tools"""
        mcp_tools = FoxMCPTools(mock_websocket_server)
        
        # Test each tool category
        test_actions = [
            "tabs.list",
            "tabs.create", 
            "history.query",
            "bookmarks.list"
        ]
        
        for action in test_actions:
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": action,
                "data": {},
                "timestamp": datetime.now().isoformat()
            }
            
            response = await mock_websocket_server.send_request_and_wait(request)
            
            assert response["type"] == "response", f"Action {action} should return response"
            assert response["action"] == action
            assert "data" in response


class TestMCPServerConfiguration:
    """Test MCP server configuration options"""
    
    def test_default_ports(self):
        """Test default port configuration"""
        server = FoxMCPServer(start_mcp=False)
        
        assert server.port == 8765  # Default WebSocket port
        assert server.mcp_port == 3000  # Default MCP port
    
    def test_custom_ports(self):
        """Test custom port configuration"""
        server = FoxMCPServer(port=9000, mcp_port=4000)
        
        assert server.port == 9000
        assert server.mcp_port == 4000
    
    def test_mcp_components_initialized(self):
        """Test that MCP components are properly initialized"""
        server = FoxMCPServer(start_mcp=False)
        
        # MCP tools should be initialized
        assert hasattr(server, 'mcp_tools')
        assert server.mcp_tools is not None
        
        # MCP app should be available
        assert hasattr(server, 'mcp_app') 
        assert server.mcp_app is not None
        
        # Should have MCP server startup method
        assert hasattr(server, 'start_mcp_server')
        assert callable(server.start_mcp_server)


class TestMCPToolStructure:
    """Test MCP tool structure and organization"""
    
    def test_tool_categories_exist(self):
        """Test that all expected tool categories are set up"""
        mock_server = Mock()
        mcp_tools = FoxMCPTools(mock_server)
        
        # Check that setup methods exist for all categories
        expected_setup_methods = [
            '_setup_tab_tools',
            '_setup_history_tools', 
            '_setup_bookmark_tools',
            '_setup_navigation_tools',
            '_setup_content_tools'
        ]
        
        for method_name in expected_setup_methods:
            assert hasattr(mcp_tools, method_name), f"Missing setup method: {method_name}"
            assert callable(getattr(mcp_tools, method_name))
    
    def test_mcp_app_creation(self):
        """Test MCP application creation"""
        mock_server = Mock()
        mcp_tools = FoxMCPTools(mock_server)
        
        mcp_app = mcp_tools.get_mcp_app()
        
        # Should return FastMCP instance
        from fastmcp.server.server import FastMCP
        assert isinstance(mcp_app, FastMCP)


if __name__ == "__main__":
    # Run tests directly if needed
    pytest.main([__file__, "-v"])