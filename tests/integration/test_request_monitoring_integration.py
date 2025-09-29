"""
Integration tests for web request monitoring
Tests the complete flow from MCP client to extension communication
"""

import pytest
import pytest_asyncio
import json
import asyncio
import uuid
import time
from datetime import datetime
from unittest.mock import Mock, AsyncMock
import sys
import os

import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from server.mcp_tools import FoxMCPTools
from port_coordinator import get_port_by_type


class TestRequestMonitoringIntegration:
    """Integration tests for web request monitoring APIs"""

    @pytest.fixture
    def mock_extension_server(self):
        """Create mock extension server that simulates Firefox extension responses"""
        class MockExtensionServer:
            def __init__(self):
                self.extension_connection = None
                self.pending_requests = {}
                self.sent_messages = []
                self.mock_responses = {
                    "requests.start_monitoring": {
                        "type": "response",
                        "data": {
                            "monitor_id": "mon_integration_test",
                            "status": "active",
                            "started_at": datetime.now().isoformat(),
                            "url_patterns": ["*"],
                            "options": {
                                "capture_request_bodies": True,
                                "capture_response_bodies": True,
                                "max_body_size": 50000
                            }
                        }
                    },
                    "requests.stop_monitoring": {
                        "type": "response",
                        "data": {
                            "monitor_id": "mon_integration_test",
                            "status": "stopped",
                            "stopped_at": datetime.now().isoformat(),
                            "total_requests_captured": 25,
                            "statistics": {
                                "duration_seconds": 30,
                                "requests_per_second": 0.83,
                                "total_data_size": 1024000
                            }
                        }
                    },
                    "requests.list_captured": {
                        "type": "response",
                        "data": {
                            "monitor_id": "mon_integration_test",
                            "total_requests": 3,
                            "requests": [
                                {
                                    "request_id": "req_int_001",
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
                                    "request_id": "req_int_002",
                                    "timestamp": "2025-01-15T10:30:18.456Z",
                                    "url": "https://api.example.com/posts",
                                    "method": "GET",
                                    "status_code": 200,
                                    "duration_ms": 180,
                                    "request_size": 0,
                                    "response_size": 2048,
                                    "content_type": "application/json",
                                    "tab_id": 123
                                },
                                {
                                    "request_id": "req_int_003",
                                    "timestamp": "2025-01-15T10:30:22.789Z",
                                    "url": "https://example.org/image.png",
                                    "method": "GET",
                                    "status_code": 200,
                                    "duration_ms": 95,
                                    "request_size": 0,
                                    "response_size": 15360,
                                    "content_type": "image/png",
                                    "tab_id": 123
                                }
                            ]
                        }
                    },
                    "requests.get_content": {
                        "type": "response",
                        "data": {
                            "request_id": "req_int_001",
                            "request_headers": {
                                "Content-Type": "application/json",
                                "Authorization": "Bearer ***",
                                "User-Agent": "Mozilla/5.0 Firefox"
                            },
                            "response_headers": {
                                "Content-Type": "application/json",
                                "Content-Length": "156",
                                "Cache-Control": "no-cache"
                            },
                            "request_body": {
                                "included": True,
                                "content": '{"name": "John Doe", "email": "john@example.org"}',
                                "content_type": "application/json",
                                "encoding": "utf8",
                                "size_bytes": 89,
                                "truncated": False,
                                "saved_to_file": None
                            },
                            "response_body": {
                                "included": True,
                                "content": '{"id": 123, "name": "John Doe", "email": "john@example.org", "created_at": "2025-01-15T10:30:15Z"}',
                                "content_type": "application/json",
                                "encoding": "utf8",
                                "size_bytes": 156,
                                "truncated": False,
                                "saved_to_file": None
                            }
                        }
                    }
                }

            async def send_request_and_wait(self, request, timeout=10.0):
                """Mock request/response simulation"""
                self.sent_messages.append(request)
                action = request.get("action", "")
                request_id = request.get("id")

                # Simulate network delay
                await asyncio.sleep(0.01)

                if action in self.mock_responses:
                    response = self.mock_responses[action].copy()
                    response["id"] = request_id
                    return response

                # Default response for unknown actions
                return {
                    "id": request_id,
                    "type": "response",
                    "data": {"mock": True, "action": action}
                }

            def set_mock_response(self, action, response):
                """Override mock response for specific action"""
                self.mock_responses[action] = response

        return MockExtensionServer()

    @pytest.fixture
    def mcp_tools(self, mock_extension_server):
        """Create FoxMCPTools with mock extension server"""
        return FoxMCPTools(mock_extension_server)

    @pytest.mark.asyncio
    async def test_complete_monitoring_workflow(self, mcp_tools, mock_extension_server):
        """Test complete workflow: start -> list -> get_content -> stop"""

        # Get tool functions
        tools = {}
        tools_dict = await mcp_tools.mcp.get_tools()
        for name, tool in tools_dict.items():
            if name.startswith("requests_"):
                tools[name] = tool.fn

        # Step 1: Start monitoring
        start_result = await tools["requests_start_monitoring"](
            url_patterns=["https://api.example.com/*", "https://example.org/*"],
            options={
                "capture_request_bodies": True,
                "capture_response_bodies": True,
                "max_body_size": 100000
            }
        )

        start_data = json.loads(start_result)
        assert "monitor_id" in start_data
        assert start_data["status"] == "active"
        monitor_id = start_data["monitor_id"]

        # Verify start request was sent correctly
        start_request = mock_extension_server.sent_messages[0]
        assert start_request["action"] == "requests.start_monitoring"
        assert "https://api.example.com/*" in start_request["data"]["url_patterns"]
        assert start_request["data"]["options"]["max_body_size"] == 100000

        # Step 2: List captured requests
        list_result = await tools["requests_list_captured"](monitor_id=monitor_id)
        list_data = json.loads(list_result)

        assert list_data["monitor_id"] == monitor_id
        assert list_data["total_requests"] == 3
        assert len(list_data["requests"]) == 3

        # Verify we have different types of requests
        request_methods = [req["method"] for req in list_data["requests"]]
        assert "POST" in request_methods
        assert "GET" in request_methods

        request_types = [req["content_type"] for req in list_data["requests"]]
        assert "application/json" in request_types
        assert "image/png" in request_types

        # Step 3: Get content for specific request
        json_request = next(req for req in list_data["requests"] if req["content_type"] == "application/json")
        content_result = await tools["requests_get_content"](
            monitor_id=monitor_id,
            request_id=json_request["request_id"],
            include_binary=True
        )

        content_data = json.loads(content_result)
        assert content_data["request_id"] == json_request["request_id"]
        assert "request_headers" in content_data
        assert "response_headers" in content_data
        assert content_data["request_body"]["included"] is True
        assert "John Doe" in content_data["request_body"]["content"]

        # Step 4: Stop monitoring
        stop_result = await tools["requests_stop_monitoring"](
            monitor_id=monitor_id,
            drain_timeout=10
        )

        stop_data = json.loads(stop_result)
        assert stop_data["monitor_id"] == monitor_id
        assert stop_data["status"] == "stopped"
        assert stop_data["total_requests_captured"] == 25
        assert "statistics" in stop_data

        # Verify all steps sent correct requests
        assert len(mock_extension_server.sent_messages) == 4
        actions = [msg["action"] for msg in mock_extension_server.sent_messages]
        expected_actions = [
            "requests.start_monitoring",
            "requests.list_captured",
            "requests.get_content",
            "requests.stop_monitoring"
        ]
        assert actions == expected_actions

    @pytest.mark.asyncio
    async def test_monitoring_with_tab_filter(self, mcp_tools, mock_extension_server):
        """Test monitoring with tab-specific filtering"""

        # Override mock response to include tab filtering
        mock_extension_server.set_mock_response("requests.start_monitoring", {
            "type": "response",
            "data": {
                "monitor_id": "mon_tab_filtered",
                "status": "active",
                "started_at": datetime.now().isoformat(),
                "url_patterns": ["*"],
                "tab_id": 456,
                "options": {"capture_request_bodies": False}
            }
        })

        start_monitoring = (await mcp_tools.mcp.get_tools())["requests_start_monitoring"].fn

        result = await start_monitoring(
            url_patterns=["*"],
            tab_id=456,
            options={"capture_request_bodies": False}
        )

        data = json.loads(result)
        assert data["tab_id"] == 456

        # Verify tab_id was sent in request
        sent_request = mock_extension_server.sent_messages[0]
        assert sent_request["data"]["tab_id"] == 456

    @pytest.mark.asyncio
    async def test_binary_content_handling(self, mcp_tools, mock_extension_server):
        """Test handling of binary content with file saving"""

        # Setup mock response for binary content
        mock_extension_server.set_mock_response("requests.get_content", {
            "type": "response",
            "data": {
                "request_id": "req_binary_test",
                "request_headers": {"Content-Type": "multipart/form-data"},
                "response_headers": {"Content-Type": "image/png", "Content-Length": "15360"},
                "request_body": {
                    "included": True,
                    "content": "LS0tLS1XZWJLaXRGb3JtQm91bmRhcnlabXdNZFZJSUQzWA==",
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
                    "size_bytes": 15360,
                    "truncated": False,
                    "saved_to_file": "/tmp/test_image.png"
                }
            }
        })

        get_content = (await mcp_tools.mcp.get_tools())["requests_get_content"].fn

        result = await get_content(
            monitor_id="mon_test",
            request_id="req_binary_test",
            include_binary=True,
            save_response_body_to="/tmp/test_image.png"
        )

        data = json.loads(result)
        assert data["request_body"]["encoding"] == "base64"
        assert data["response_body"]["saved_to_file"] == "/tmp/test_image.png"
        assert data["response_body"]["included"] is False  # Saved to file, not included

        # Verify file saving parameters were sent
        sent_request = mock_extension_server.sent_messages[0]
        assert sent_request["data"]["include_binary"] is True
        assert sent_request["data"]["save_response_body_to"] == "/tmp/test_image.png"

    @pytest.mark.asyncio
    async def test_error_scenarios(self, mcp_tools, mock_extension_server):
        """Test various error scenarios"""

        # Test invalid monitor_id
        mock_extension_server.set_mock_response("requests.list_captured", {
            "type": "error",
            "data": {"message": "Monitor session not found"}
        })

        list_captured = (await mcp_tools.mcp.get_tools())["requests_list_captured"].fn
        result = await list_captured(monitor_id="invalid_monitor")

        data = json.loads(result)
        assert "error" in data
        assert "Monitor session not found" in data["error"]

        # Test empty URL patterns
        start_monitoring = (await mcp_tools.mcp.get_tools())["requests_start_monitoring"].fn
        result = await start_monitoring(url_patterns=[])

        data = json.loads(result)
        assert "error" in data
        assert "url_patterns is required" in data["error"]

    @pytest.mark.asyncio
    async def test_monitoring_performance_data(self, mcp_tools, mock_extension_server):
        """Test that performance and timing data is properly captured"""

        list_captured = (await mcp_tools.mcp.get_tools())["requests_list_captured"].fn
        result = await list_captured(monitor_id="mon_test")

        data = json.loads(result)
        requests = data["requests"]

        # Verify performance data is present
        for request in requests:
            assert "duration_ms" in request
            assert "timestamp" in request
            assert "request_size" in request
            assert "response_size" in request
            assert request["duration_ms"] > 0

        # Check for variety in performance data
        durations = [req["duration_ms"] for req in requests]
        assert len(set(durations)) > 1  # Different requests have different durations

    @pytest.mark.asyncio
    async def test_concurrent_monitoring_requests(self, mcp_tools, mock_extension_server):
        """Test handling of concurrent monitoring API requests"""

        tools = {
            name: tool.fn for name, tool in (await mcp_tools.mcp.get_tools()).items()
            if name.startswith("requests_")
        }

        # Start multiple concurrent requests
        tasks = [
            tools["requests_start_monitoring"](url_patterns=["*"]),
            tools["requests_list_captured"](monitor_id="mon_test"),
            tools["requests_get_content"](monitor_id="mon_test", request_id="req_001")
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete without exceptions
        for result in results:
            assert not isinstance(result, Exception)
            data = json.loads(result)
            assert "error" not in data or "mock" in data  # Either valid response or mock response

        # Verify all requests were sent
        assert len(mock_extension_server.sent_messages) >= 3