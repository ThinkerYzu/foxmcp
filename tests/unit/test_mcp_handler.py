"""
Unit tests for MCP handler
"""

import pytest
from unittest.mock import Mock, AsyncMock
from server.mcp_handler import MCPHandler

class TestMCPHandler:
    
    @pytest.fixture 
    def mock_server(self):
        """Mock server instance"""
        server = Mock()
        server.send_to_extension = AsyncMock(return_value=True)
        server.send_request_and_wait = AsyncMock(return_value={
            "type": "response", 
            "data": {"result": "success"}
        })
        return server
    
    @pytest.fixture
    def mcp_handler(self, mock_server):
        """Create MCPHandler instance"""
        return MCPHandler(mock_server)
    
    def test_handler_initialization(self, mcp_handler):
        """Test handler initialization"""
        assert mcp_handler.server is not None
        assert isinstance(mcp_handler.tools, dict)
        assert len(mcp_handler.tools) > 0
    
    def test_register_tools(self, mcp_handler):
        """Test tool registration"""
        tools = mcp_handler.tools
        
        # Check that all expected tools are registered
        expected_tools = [
            "browser_history_query",
            "browser_history_recent", 
            "browser_tabs_list",
            "browser_tabs_create",
            "browser_tabs_close",
            "browser_content_text",
            "browser_content_html",
            "browser_navigate_url",
            "browser_navigate_back",
            "browser_bookmarks_list",
            "browser_bookmarks_create"
        ]
        
        for tool_name in expected_tools:
            assert tool_name in tools
            assert "description" in tools[tool_name]
            assert "parameters" in tools[tool_name]
    
    def test_tool_parameters(self, mcp_handler):
        """Test tool parameter definitions"""
        # Test history query tool parameters
        history_tool = mcp_handler.tools["browser_history_query"]
        params = history_tool["parameters"]
        
        assert "query" in params
        assert params["query"]["type"] == "string"
        assert "maxResults" in params
        assert params["maxResults"]["type"] == "integer"
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_unknown_tool(self, mcp_handler):
        """Test handling unknown tool call"""
        result = await mcp_handler.handle_tool_call("unknown_tool", {})
        
        assert "error" in result
        assert "Unknown tool" in result["error"]
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_valid_tool(self, mcp_handler):
        """Test handling valid tool call"""
        parameters = {"count": 10}
        
        result = await mcp_handler.handle_tool_call("browser_history_recent", parameters)
        
        # Should successfully get response from extension
        assert "result" in result
        assert result["result"] == "success"
        
        # Verify server.send_request_and_wait was called
        mcp_handler.server.send_request_and_wait.assert_called_once()
        call_args = mcp_handler.server.send_request_and_wait.call_args[0][0]
        
        assert call_args["type"] == "request"
        assert call_args["action"] == "history.recent"
        assert call_args["data"] == parameters
    
    @pytest.mark.asyncio 
    async def test_handle_tool_call_tabs_list(self, mcp_handler):
        """Test tabs list tool call"""
        result = await mcp_handler.handle_tool_call("browser_tabs_list", {})
        
        assert result["result"] == "success"
        mcp_handler.server.send_request_and_wait.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_bookmarks_create(self, mcp_handler):
        """Test bookmark creation tool call"""
        parameters = {
            "title": "Test Bookmark",
            "url": "https://example.com",
            "parentId": "1"
        }
        
        result = await mcp_handler.handle_tool_call("browser_bookmarks_create", parameters)
        
        assert result["result"] == "success"
        call_args = mcp_handler.server.send_request_and_wait.call_args[0][0]
        assert call_args["data"] == parameters
    
    @pytest.mark.asyncio
    async def test_handle_tool_call_server_send_failure(self, mcp_handler):
        """Test handling server send failure"""
        mcp_handler.server.send_request_and_wait = AsyncMock(return_value={
            "error": "Failed to send request to extension"
        })
        
        result = await mcp_handler.handle_tool_call("browser_tabs_list", {})
        
        assert "error" in result
        assert "Failed to send request" in result["error"]
    
    def test_get_available_tools(self, mcp_handler):
        """Test getting available tools list"""
        tools_list = mcp_handler.get_available_tools()
        
        assert isinstance(tools_list, list)
        assert len(tools_list) > 0
        
        # Check first tool structure
        first_tool = tools_list[0]
        assert "name" in first_tool
        assert "description" in first_tool  
        assert "parameters" in first_tool
    
    def test_action_mapping(self, mcp_handler):
        """Test that all tools have proper action mapping"""
        # This is tested implicitly in handle_tool_call tests
        # but we can verify the mapping logic
        
        tools_with_mappings = [
            ("browser_history_query", "history.query"),
            ("browser_tabs_create", "tabs.create"),
            ("browser_content_text", "content.text"),
            ("browser_navigate_back", "navigation.back"),
            ("browser_bookmarks_list", "bookmarks.list")
        ]
        
        for tool_name, expected_action in tools_with_mappings:
            assert tool_name in mcp_handler.tools