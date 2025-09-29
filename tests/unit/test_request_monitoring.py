"""
Unit tests for web request monitoring APIs
Tests the MCP tools without WebSocket communication
"""

import pytest
import json
import asyncio
import uuid
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class TestRequestMonitoringAPIs:
    """Test web request monitoring MCP tools"""

    @pytest.fixture
    def mock_websocket_server(self):
        """Create mock WebSocket server for testing"""
        class MockServer:
            def __init__(self):
                self.extension_connection = None
                self.pending_requests = {}
                self.sent_messages = []
                self.mock_responses = {}

            def set_mock_response(self, action, response):
                """Set mock response for specific action"""
                self.mock_responses[action] = response

            async def send_request_and_wait(self, request, timeout=10.0):
                """Mock WebSocket communication"""
                action = request.get("action", "")
                self.sent_messages.append(request)

                if action in self.mock_responses:
                    return self.mock_responses[action]

                # Default response
                return {
                    "type": "response",
                    "data": {"mock": True, "action": action}
                }

        return MockServer()

    @pytest.fixture
    def mcp_tools(self, mock_websocket_server):
        """Create FoxMCPTools instance with mock server"""
        return FoxMCPTools(mock_websocket_server)

    @pytest.mark.asyncio
    async def test_requests_start_monitoring_success(self, mcp_tools, mock_websocket_server):
        """Test successful start monitoring request"""
        # Set up mock response
        mock_response = {
            "type": "response",
            "data": {
                "monitor_id": "mon_test123",
                "status": "active",
                "started_at": "2025-01-15T10:30:00.000Z",
                "url_patterns": ["https://api.example.com/*"],
                "options": {"capture_request_bodies": True}
            }
        }
        mock_websocket_server.set_mock_response("requests.start_monitoring", mock_response)

        # Get the monitoring function
        tools_dict = await mcp_tools.mcp.get_tools()
        start_monitoring = tools_dict.get("requests_start_monitoring").fn

        assert start_monitoring is not None, "requests_start_monitoring tool not found"

        # Test the function
        result = await start_monitoring(
            url_patterns=["https://api.example.com/*"],
            options={"capture_request_bodies": True},
            tab_id=None
        )

        # Verify result
        response_data = json.loads(result)
        assert response_data["monitor_id"] == "mon_test123"
        assert response_data["status"] == "active"

        # Verify request was sent correctly
        assert len(mock_websocket_server.sent_messages) == 1
        sent_request = mock_websocket_server.sent_messages[0]
        assert sent_request["action"] == "requests.start_monitoring"
        assert sent_request["data"]["url_patterns"] == ["https://api.example.com/*"]

    @pytest.mark.asyncio
    async def test_requests_start_monitoring_with_tab_id(self, mcp_tools, mock_websocket_server):
        """Test start monitoring with specific tab ID"""
        mock_response = {
            "type": "response",
            "data": {"monitor_id": "mon_tab456", "status": "active"}
        }
        mock_websocket_server.set_mock_response("requests.start_monitoring", mock_response)

        start_monitoring = None
        tools_dict = await mcp_tools.mcp.get_tools()
        for name, tool in tools_dict.items():
            if name == "requests_start_monitoring":
                start_monitoring = tool.fn
                break

        result = await start_monitoring(
            url_patterns=["*/api/*"],
            tab_id=123
        )

        # Verify tab_id was included in request
        sent_request = mock_websocket_server.sent_messages[0]
        assert sent_request["data"]["tab_id"] == 123

    @pytest.mark.asyncio
    async def test_requests_start_monitoring_empty_patterns(self, mcp_tools, mock_websocket_server):
        """Test start monitoring with empty URL patterns"""
        start_monitoring = None
        tools_dict = await mcp_tools.mcp.get_tools()
        for name, tool in tools_dict.items():
            if name == "requests_start_monitoring":
                start_monitoring = tool.fn
                break

        result = await start_monitoring(url_patterns=[])
        response_data = json.loads(result)
        assert "error" in response_data
        assert "url_patterns is required" in response_data["error"]

    @pytest.mark.asyncio
    async def test_requests_stop_monitoring_success(self, mcp_tools, mock_websocket_server):
        """Test successful stop monitoring request"""
        mock_response = {
            "type": "response",
            "data": {
                "monitor_id": "mon_test123",
                "status": "stopped",
                "total_requests_captured": 42,
                "statistics": {"duration_seconds": 300}
            }
        }
        mock_websocket_server.set_mock_response("requests.stop_monitoring", mock_response)

        stop_monitoring = None
        tools_dict = await mcp_tools.mcp.get_tools()
        for name, tool in tools_dict.items():
            if name == "requests_stop_monitoring":
                stop_monitoring = tool.fn
                break

        result = await stop_monitoring(
            monitor_id="mon_test123",
            drain_timeout=10
        )

        response_data = json.loads(result)
        assert response_data["monitor_id"] == "mon_test123"
        assert response_data["status"] == "stopped"
        assert response_data["total_requests_captured"] == 42

        # Verify request parameters
        sent_request = mock_websocket_server.sent_messages[0]
        assert sent_request["data"]["monitor_id"] == "mon_test123"
        assert sent_request["data"]["drain_timeout"] == 10

    @pytest.mark.asyncio
    async def test_requests_list_captured_success(self, mcp_tools, mock_websocket_server):
        """Test successful list captured requests"""
        mock_response = {
            "type": "response",
            "data": {
                "monitor_id": "mon_test123",
                "total_requests": 2,
                "requests": [
                    {
                        "request_id": "req_001",
                        "timestamp": "2025-01-15T10:30:15.123Z",
                        "url": "https://api.example.com/users",
                        "method": "POST",
                        "status_code": 201,
                        "duration_ms": 245,
                        "request_size": 89,
                        "response_size": 156,
                        "content_type": "application/json",
                        "tab_id": 123
                    },
                    {
                        "request_id": "req_002",
                        "timestamp": "2025-01-15T10:30:20.456Z",
                        "url": "https://api.example.com/posts",
                        "method": "GET",
                        "status_code": 200,
                        "duration_ms": 180,
                        "request_size": 0,
                        "response_size": 2048,
                        "content_type": "application/json",
                        "tab_id": 123
                    }
                ]
            }
        }
        mock_websocket_server.set_mock_response("requests.list_captured", mock_response)

        list_captured = None
        tools_dict = await mcp_tools.mcp.get_tools()
        for name, tool in tools_dict.items():
            if name == "requests_list_captured":
                list_captured = tool.fn
                break

        result = await list_captured(monitor_id="mon_test123")

        response_data = json.loads(result)
        assert response_data["total_requests"] == 2
        assert len(response_data["requests"]) == 2
        assert response_data["requests"][0]["request_id"] == "req_001"

    @pytest.mark.asyncio
    async def test_requests_get_content_default_options(self, mcp_tools, mock_websocket_server):
        """Test get content with default options"""
        mock_response = {
            "type": "response",
            "data": {
                "request_id": "req_001",
                "request_headers": {"Content-Type": "application/json"},
                "response_headers": {"Content-Type": "application/json"},
                "request_body": {
                    "included": False,
                    "content": None,
                    "content_type": "application/json",
                    "encoding": None,
                    "size_bytes": 89,
                    "truncated": False,
                    "saved_to_file": None
                },
                "response_body": {
                    "included": False,
                    "content": None,
                    "content_type": "application/json",
                    "encoding": None,
                    "size_bytes": 156,
                    "truncated": False,
                    "saved_to_file": None
                }
            }
        }
        mock_websocket_server.set_mock_response("requests.get_content", mock_response)

        get_content = None
        tools_dict = await mcp_tools.mcp.get_tools()
        for name, tool in tools_dict.items():
            if name == "requests_get_content":
                get_content = tool.fn
                break

        result = await get_content(
            monitor_id="mon_test123",
            request_id="req_001"
        )

        response_data = json.loads(result)
        assert response_data["request_id"] == "req_001"
        assert response_data["request_body"]["included"] is False
        assert response_data["response_body"]["included"] is False

        # Verify default parameters
        sent_request = mock_websocket_server.sent_messages[0]
        assert sent_request["data"]["include_binary"] is False

    @pytest.mark.asyncio
    async def test_requests_get_content_with_binary_and_files(self, mcp_tools, mock_websocket_server):
        """Test get content with binary encoding and file saving"""
        mock_response = {
            "type": "response",
            "data": {
                "request_id": "req_002",
                "request_headers": {"Content-Type": "multipart/form-data"},
                "response_headers": {"Content-Type": "image/png"},
                "request_body": {
                    "included": True,
                    "content": "LS0tLS1XZWJLaXRGb3JtQm91bmRhcnk=",
                    "content_type": "multipart/form-data",
                    "encoding": "base64",
                    "size_bytes": 1024,
                    "truncated": False,
                    "saved_to_file": None
                },
                "response_body": {
                    "included": False,
                    "content": None,
                    "content_type": "image/png",
                    "encoding": None,
                    "size_bytes": 2048,
                    "truncated": False,
                    "saved_to_file": "/tmp/response.png"
                }
            }
        }
        mock_websocket_server.set_mock_response("requests.get_content", mock_response)

        get_content = None
        tools_dict = await mcp_tools.mcp.get_tools()
        for name, tool in tools_dict.items():
            if name == "requests_get_content":
                get_content = tool.fn
                break

        result = await get_content(
            monitor_id="mon_test123",
            request_id="req_002",
            include_binary=True,
            save_request_body_to="/tmp/request.bin",
            save_response_body_to="/tmp/response.png"
        )

        response_data = json.loads(result)
        assert response_data["request_body"]["encoding"] == "base64"
        assert response_data["response_body"]["saved_to_file"] == "/tmp/response.png"

        # Verify all parameters were sent
        sent_request = mock_websocket_server.sent_messages[0]
        assert sent_request["data"]["include_binary"] is True
        assert sent_request["data"]["save_request_body_to"] == "/tmp/request.bin"
        assert sent_request["data"]["save_response_body_to"] == "/tmp/response.png"

    @pytest.mark.asyncio
    async def test_requests_error_handling(self, mcp_tools, mock_websocket_server):
        """Test error handling in monitoring APIs"""
        # Test extension error response
        mock_response = {
            "type": "error",
            "data": {"message": "Invalid monitor_id"}
        }
        mock_websocket_server.set_mock_response("requests.stop_monitoring", mock_response)

        stop_monitoring = None
        tools_dict = await mcp_tools.mcp.get_tools()
        for name, tool in tools_dict.items():
            if name == "requests_stop_monitoring":
                stop_monitoring = tool.fn
                break

        result = await stop_monitoring(monitor_id="invalid_id")
        response_data = json.loads(result)
        assert "error" in response_data
        assert "Invalid monitor_id" in response_data["error"]

    @pytest.mark.asyncio
    async def test_requests_websocket_communication_error(self, mcp_tools, mock_websocket_server):
        """Test handling of WebSocket communication errors"""
        # Mock WebSocket error
        mock_websocket_server.set_mock_response("requests.start_monitoring", {"error": "Connection failed"})

        start_monitoring = None
        tools_dict = await mcp_tools.mcp.get_tools()
        for name, tool in tools_dict.items():
            if name == "requests_start_monitoring":
                start_monitoring = tool.fn
                break

        result = await start_monitoring(url_patterns=["*"])
        response_data = json.loads(result)
        assert "error" in response_data
        assert "Connection failed" in response_data["error"]

    @pytest.mark.asyncio
    async def test_requests_tools_registration(self, mcp_tools):
        """Test that all monitoring tools are properly registered"""
        tools_dict = await mcp_tools.mcp.get_tools()
        tool_names = list(tools_dict.keys())

        expected_tools = [
            "requests_start_monitoring",
            "requests_stop_monitoring",
            "requests_list_captured",
            "requests_get_content"
        ]

        for tool in expected_tools:
            assert tool in tool_names, f"Tool {tool} not registered"

    @pytest.mark.asyncio
    async def test_requests_tools_are_async(self, mcp_tools):
        """Test that all monitoring tools are async functions"""
        monitoring_tools = [
            "requests_start_monitoring",
            "requests_stop_monitoring",
            "requests_list_captured",
            "requests_get_content"
        ]

        tools_dict = await mcp_tools.mcp.get_tools()
        for tool_name in monitoring_tools:
            tool = tools_dict.get(tool_name)
            assert tool is not None, f"Tool {tool_name} not found"
            assert asyncio.iscoroutinefunction(tool.fn), f"Tool {tool_name} is not async"