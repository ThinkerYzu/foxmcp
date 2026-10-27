from server.browser_profile import BrowserProfile
from test_config import profile_connection
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
        tools_dict = {tool.name: tool for tool in await mcp_tools.mcp.list_tools()}
        for name, tool in tools_dict.items():
            if name.startswith("requests_"):
                tools[name] = tool.fn

        # Step 1: Start monitoring
        start_result = await tools["requests_start_monitoring"](profile_id="test-profile",
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
        list_result = await tools["requests_list_captured"](profile_id="test-profile", monitor_id=monitor_id)
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
        content_result = await tools["requests_get_content"](profile_id="test-profile",
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
        stop_result = await tools["requests_stop_monitoring"](profile_id="test-profile",
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

        start_monitoring = (await mcp_tools.mcp.get_tool("requests_start_monitoring")).fn

        result = await start_monitoring(profile_id="test-profile",
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

        get_content = (await mcp_tools.mcp.get_tool("requests_get_content")).fn

        result = await get_content(profile_id="test-profile",
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

        list_captured = (await mcp_tools.mcp.get_tool("requests_list_captured")).fn
        result = await list_captured(profile_id="test-profile", monitor_id="invalid_monitor")

        data = json.loads(result)
        assert "error" in data
        assert "Monitor session not found" in data["error"]

        # Test empty URL patterns
        start_monitoring = (await mcp_tools.mcp.get_tool("requests_start_monitoring")).fn
        result = await start_monitoring(profile_id="test-profile", url_patterns=[])

        data = json.loads(result)
        assert "error" in data
        assert "url_patterns is required" in data["error"]

    @pytest.mark.asyncio
    async def test_monitoring_performance_data(self, mcp_tools, mock_extension_server):
        """Test that performance and timing data is properly captured"""

        list_captured = (await mcp_tools.mcp.get_tool("requests_list_captured")).fn
        result = await list_captured(profile_id="test-profile", monitor_id="mon_test")

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
            tool.name: tool.fn for tool in await mcp_tools.mcp.list_tools()
            if tool.name.startswith("requests_")
        }

        # Start multiple concurrent requests
        tasks = [
            tools["requests_start_monitoring"](profile_id="test-profile", url_patterns=["*"]),
            tools["requests_list_captured"](profile_id="test-profile", monitor_id="mon_test"),
            tools["requests_get_content"](profile_id="test-profile", monitor_id="mon_test", request_id="req_001")
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should complete without exceptions
        for result in results:
            assert not isinstance(result, Exception)
            data = json.loads(result)
            assert "error" not in data or "mock" in data  # Either valid response or mock response

        # Verify all requests were sent
        assert len(mock_extension_server.sent_messages) >= 3

class TestMonitorsFollowTheirClient:
    """A monitor belongs to the MCP client that started it, and ends when it goes"""

    @pytest.mark.asyncio
    async def test_monitor_stops_when_its_mcp_client_disconnects(self):
        """The server stops a departed client's monitors, and only those

        A monitor lives in the extension, which outlives every MCP client, and
        only the client that started one knows its id. Left behind it keeps the
        extension's webRequest listeners registered for a reader that will never
        come back.

        Both directions are checked here because a reaper that stopped monitors
        indiscriminately would pass the first assertion on its own.
        """
        from fastmcp import Client
        from test_config import connect_as_extension

        websocket_port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')

        server = FoxMCPServer(host="localhost", port=websocket_port,
                              mcp_port=mcp_port, start_mcp=True)
        server.MONITOR_REAP_INTERVAL = 0.5
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(1.0)

        stop_requests = asyncio.Queue()

        async def answer_as_extension(extension):
            """Stand in for the extension: hand out a monitor id, note the stops"""
            while True:
                request = json.loads(await extension.recv())
                if request.get('type') == 'hello':
                    continue
                action = request['action']

                if action == 'requests.start_monitoring':
                    data = {'monitor_id': 'mon_owned', 'status': 'active'}
                elif action == 'requests.stop_monitoring':
                    await stop_requests.put(request['data']['monitor_id'])
                    data = {'monitor_id': request['data']['monitor_id'], 'status': 'stopped',
                            'total_requests_captured': 0}
                else:
                    data = {}

                await extension.send(json.dumps({
                    'id': request['id'], 'type': 'response', 'action': action, 'data': data
                }))

        try:
            async with connect_as_extension(f"ws://localhost:{websocket_port}") as extension:
                responder = asyncio.create_task(answer_as_extension(extension))
                await asyncio.sleep(0.3)

                try:
                    async with Client(f"http://localhost:{mcp_port}/mcp") as client:
                        await client.call_tool('requests_start_monitoring',
                                               {'profile_id': extension.profile_id, 'url_patterns': ['*']})

                        assert 'mon_owned' in profile_connection(server).monitor_owners, \
                            "The monitor should be tied to the client that started it"

                        # Several reaper passes with the client still connected
                        await asyncio.sleep(2.0)
                        assert stop_requests.empty(), \
                            "A monitor was stopped while its client was still connected"

                    stopped = await asyncio.wait_for(stop_requests.get(), timeout=10.0)
                    assert stopped == 'mon_owned', f"Wrong monitor stopped: {stopped}"
                    assert not profile_connection(server).monitor_owners, \
                        f"Ownership record outlived the monitor: {profile_connection(server).monitor_owners}"
                finally:
                    responder.cancel()
        finally:
            await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_a_monitor_the_server_never_recorded_is_stopped(self):
        """A reply naming a monitor no client owns has that monitor stopped

        The two sides can drift only if one lets go of a monitor the other keeps:
        an extension too old to clear its monitors when a connection ends, or a
        server that has forgotten an owner. Whichever way round, the monitor is
        capturing for a reader that cannot reach it.

        Driven through handle_extension_message rather than a live browser,
        because a matched pair of halves never produces the message under test.
        """
        websocket_port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')

        server = BrowserProfile(FoxMCPServer(host="localhost", port=websocket_port,
                              mcp_port=mcp_port, start_mcp=False), None, "test-profile", "moz-extension://test")

        sent = []

        async def record_request(request, timeout=30.0):
            sent.append(request)
            return {'type': 'response', 'action': request['action'],
                    'data': {'monitor_id': request['data']['monitor_id'], 'status': 'stopped'}}

        server.send_request_and_wait = record_request

        listing = json.dumps({
            'id': 'some-request', 'type': 'response', 'action': 'requests.list_captured',
            'data': {'monitor_id': 'mon_stray', 'total_requests': 3, 'requests': []}
        })
        await server.handle_extension_message(listing)
        await asyncio.sleep(0.2)

        assert [r['action'] for r in sent] == ['requests.stop_monitoring'], \
            f"The stray monitor should have been stopped once: {sent}"
        assert sent[0]['data']['monitor_id'] == 'mon_stray'

        # A monitor the server does know about is left alone
        sent.clear()
        server.register_monitor('mon_owned', 'a-session')
        await server.handle_extension_message(json.dumps({
            'id': 'another-request', 'type': 'response', 'action': 'requests.list_captured',
            'data': {'monitor_id': 'mon_owned', 'total_requests': 1, 'requests': []}
        }))
        await asyncio.sleep(0.2)

        assert sent == [], f"A monitor with an owner must not be stopped: {sent}"

    @pytest.mark.asyncio
    async def test_starting_a_monitor_does_not_stop_it(self):
        """The reply that creates a monitor is not evidence that it is a stray

        The owner is recorded from the tool, after the extension's reply has been
        handled, so for the length of that gap the new monitor is absent from the
        registry. Reading the reply as a stray would stop every monitor at birth.
        """
        websocket_port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')

        server = BrowserProfile(FoxMCPServer(host="localhost", port=websocket_port,
                              mcp_port=mcp_port, start_mcp=False), None, "test-profile", "moz-extension://test")

        sent = []

        async def record_request(request, timeout=30.0):
            sent.append(request)
            return {'type': 'response', 'data': {}}

        server.send_request_and_wait = record_request

        for action in ('requests.start_monitoring', 'requests.stop_monitoring'):
            await server.handle_extension_message(json.dumps({
                'id': f'reply-for-{action}', 'type': 'response', 'action': action,
                'data': {'monitor_id': 'mon_fresh', 'status': 'active'}
            }))
        await asyncio.sleep(0.2)

        assert sent == [], f"Lifecycle replies must not be read as strays: {sent}"

    @pytest.mark.asyncio
    async def test_live_sessions_unknown_reaps_nothing(self):
        """With no way to tell which clients are connected, no monitor is stopped

        `_live_mcp_session_ids` reads a private attribute of the MCP SDK's session
        manager. If a version moves it, the answer is None, and None must not be
        read as "every client has gone" - that would stop monitors of clients that
        are sitting right there.
        """
        websocket_port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')

        server = BrowserProfile(FoxMCPServer(host="localhost", port=websocket_port,
                              mcp_port=mcp_port, start_mcp=False), None, "test-profile", "moz-extension://test")
        server.register_monitor('mon_orphan', 'session-that-is-long-gone')

        sent = []

        async def record_request(request, timeout=30.0):
            sent.append(request)
            return {'type': 'response', 'data': {}}

        server.send_request_and_wait = record_request
        server.extension_connection = object()

        assert server._live_mcp_session_ids() is None, \
            "No MCP app means no answer, not an empty set of clients"

        await server.stop_monitors_of_gone_clients()

        assert sent == [], "Nothing may be stopped on an unknown answer"
        assert 'mon_orphan' in profile_connection(server).monitor_owners
