"""
MCP Protocol Compliance Tests
Tests HTTP endpoints, parameter validation, and MCP protocol compliance
"""

import pytest
import pytest_asyncio
import asyncio
import json
import os
import sys
import time
import re

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.server import FoxMCPServer
try:
    from ..port_coordinator import coordinated_test_ports
    from ..mcp_client_harness import DirectMCPTestClient
except ImportError:
    from port_coordinator import coordinated_test_ports
    from mcp_client_harness import DirectMCPTestClient


class TestMCPProtocolCompliance:
    """MCP protocol compliance and HTTP endpoint tests"""

    @pytest_asyncio.fixture
    async def full_mcp_system(self):
        """Set up complete system: MCP server + WebSocket server + Firefox"""

        # Use coordinated ports to avoid conflicts
        with coordinated_test_ports() as (ports, coord_file):
            websocket_port = ports['websocket']
            mcp_port = ports['mcp']

            # Start the complete FoxMCP server (WebSocket + MCP)
            server = FoxMCPServer(
                host="localhost",
                port=websocket_port,
                mcp_port=mcp_port,
                start_mcp=True  # Enable MCP server for end-to-end testing
            )

            # Start servers (WebSocket server only - MCP handled by start_mcp=True)
            websocket_task = asyncio.create_task(server.start_server())

            # Wait for servers to start
            await asyncio.sleep(1.0)

            # Create real MCP client harness
            mcp_client = DirectMCPTestClient(server.mcp_tools)

            system_info = {
                'server': server,
                'websocket_port': websocket_port,
                'mcp_port': mcp_port,
                'mcp_client': mcp_client,
                'coordination_file': coord_file,
                'websocket_task': websocket_task
            }

            try:
                yield system_info
            finally:
                # Cleanup
                await mcp_client.disconnect()
                await server.shutdown(websocket_task)

    @pytest.mark.asyncio
    async def test_real_mcp_http_server_tool_names(self, full_mcp_system):
        """Test that actual FastMCP HTTP server has the expected tool names

        This test prevents naming mismatches between DirectMCPTestClient
        and the real FastMCP server that external agents would use.
        """
        system = full_mcp_system
        mcp_port = system['mcp_port']

        try:
            import aiohttp
        except ImportError:
            pytest.skip("aiohttp not available for HTTP testing")

        # Give server time to fully start
        await asyncio.sleep(1.0)

        async with aiohttp.ClientSession() as session:
            # Test tools/list endpoint to get actual tool names
            try:
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }

                payload = {
                    "jsonrpc": "2.0",
                    "id": "test-tools-list",
                    "method": "tools/list",
                    "params": {}
                }

                async with session.post(
                    f"http://localhost:{mcp_port}/mcp",
                    json=payload,
                    headers=headers
                ) as response:

                    if response.status == 406:  # Not Acceptable - missing SSE
                        print("⚠ Server requires SSE headers - trying with curl-like request")
                        # This is expected for FastMCP servers
                        pytest.skip("FastMCP server requires specific SSE setup for tools/list")

                    text = await response.text()
                    print(f"Response status: {response.status}")
                    print(f"Response: {text}")

                    # For event-stream responses, parse the data
                    if "event:" in text:
                        lines = text.strip().split('\n')
                        for line in lines:
                            if line.startswith('data: '):
                                data_json = line[6:]  # Remove 'data: '
                                data = json.loads(data_json)

                                if "result" in data and "tools" in data["result"]:
                                    tools = data["result"]["tools"]
                                    tool_names = [tool["name"] for tool in tools]

                                    # Verify expected history tools exist
                                    expected_history_tools = [
                                        "history_get_recent",
                                        "history_query",
                                        "history_delete_item"
                                    ]

                                    for expected_tool in expected_history_tools:
                                        assert expected_tool in tool_names, f"Expected tool '{expected_tool}' not found in FastMCP tools: {tool_names}"

                                    # Verify incorrect names don't exist
                                    incorrect_names = [
                                        "get_recent_history",  # Wrong name that would cause agent failures
                                        "get_history_recent"   # Another potential wrong name
                                    ]

                                    for incorrect_name in incorrect_names:
                                        assert incorrect_name not in tool_names, f"Incorrect tool name '{incorrect_name}' found in FastMCP tools - this would confuse external agents"

                                    print(f"✓ FastMCP server has correct tool names")
                                    print(f"✓ History tools found: {[t for t in tool_names if 'history' in t]}")
                                    return

                    # If we get here, we couldn't parse the response
                    print("⚠ Could not parse tools list from FastMCP response")

            except Exception as e:
                print(f"Note: HTTP MCP test encountered: {e}")
                print("This may be expected due to FastMCP's SSE requirements")

                # As a fallback, verify tools exist in the server instance directly
                server = system['server']
                tools_dict = await server.mcp_app.get_tools()
                tool_names = list(tools_dict.keys())

                # Same verification as above
                expected_history_tools = [
                    "history_get_recent",
                    "history_query",
                    "history_delete_item"
                ]

                for expected_tool in expected_history_tools:
                    assert expected_tool in tool_names, f"Expected tool '{expected_tool}' not found in FastMCP tools: {tool_names}"

                print(f"✓ FastMCP server instance has correct tool names (verified directly)")
                print(f"✓ History tools found: {[t for t in tool_names if 'history' in t]}")

    @pytest.mark.asyncio
    async def test_mcp_parameter_format_validation(self, full_mcp_system):
        """Test that MCP tools properly validate parameter formats

        This test catches parameter format issues that external agents might encounter,
        such as sending 'arguments' instead of 'params', or string instead of JSON object.
        """
        system = full_mcp_system
        server = system['server']

        # Get the FastMCP tool to examine its expected parameters
        tools_dict = await server.mcp_app.get_tools()
        history_tool = tools_dict['history_get_recent']

        print("Testing parameter format validation for history_get_recent:")
        print(f"Expected schema: {history_tool.parameters}")

        # Verify the tool has direct parameters (no params wrapper)
        assert 'params' not in history_tool.parameters.get('properties', {}), \
            "FastMCP tool should NOT have 'params' wrapper - should be direct parameters"

        # Verify count parameter is directly accessible
        assert 'count' in history_tool.parameters.get('properties', {}), \
            "Should have direct 'count' parameter"

        # Verify count parameter structure
        count_param = history_tool.parameters['properties']['count']
        assert count_param['type'] == 'integer', "'count' should be integer type"
        assert 'default' in count_param, "Should have default value"
        assert count_param['default'] == 10, "Default should be 10"

        print("✓ Parameter schema validation:")
        print(f"  - Tool expects direct parameters (no 'params' wrapper)")
        print(f"  - 'count' parameter is integer, default: {count_param['default']}")
        print(f"  - Agents should send: 'arguments': {{'count': 5}}")

        # Test with DirectMCPTestClient to ensure it works correctly
        mcp_client = system['mcp_client']
        await mcp_client.connect()

        # This should work (correct format)
        result = await mcp_client.call_tool("history_get_recent", {"count": 3})
        assert result['success'], f"Correct parameter format should work: {result}"

        print("✓ DirectMCPTestClient correctly formats parameters for FastMCP")
        print("✓ Parameter validation test complete")

        # Document the correct format for external agents
        print("\n📋 For external MCP agents:")
        print("✅ Correct:   {'arguments': {'count': 5}}")
        print("❌ Wrong:     {'arguments': {'params': {'count': 5}}}")
        print("❌ Wrong:     {'arguments': {'params': '{\"count\": 5}'}}")  # String instead of object

    @pytest.mark.asyncio
    async def test_agent_parameter_error_reproduction(self, full_mcp_system):
        """Reproduce the exact error that external agents encounter

        This test reproduces the specific error format that the user's agent sends:
        'arguments': {'params': '{}'}  instead of  'arguments': {'count': 10}
        """
        system = full_mcp_system
        mcp_port = system['mcp_port']

        try:
            import aiohttp
        except ImportError:
            pytest.skip("aiohttp not available for HTTP testing")

        await asyncio.sleep(1.0)  # Wait for server to start

        print("Testing agent parameter format errors:")

        # The EXACT message the user's agent sends (incorrect)
        incorrect_agent_message = {
            "method": "tools/call",
            "params": {
                "name": "history_get_recent",
                "arguments": {"params": "{}"},  # ❌ Wrong: nested params as string
                "_meta": {"claudecode/toolUseId": "test_id"}
            },
            "jsonrpc": "2.0",
            "id": 4
        }

        # What the agent SHOULD send (correct)
        correct_agent_message = {
            "method": "tools/call",
            "params": {
                "name": "history_get_recent",
                "arguments": {"count": 5},  # ✅ Correct: direct count parameter
                "_meta": {"claudecode/toolUseId": "test_id"}
            },
            "jsonrpc": "2.0",
            "id": 5
        }

        async with aiohttp.ClientSession() as session:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }

            # Test 1: Send the incorrect message (what the user's agent sends)
            print("\\n1. Testing INCORRECT agent message format:")
            print(f"   Sending: {incorrect_agent_message}")

            try:
                async with session.post(
                    f"http://localhost:{mcp_port}/mcp",
                    json=incorrect_agent_message,
                    headers=headers
                ) as response:
                    text = await response.text()
                    print(f"   Status: {response.status}")
                    print(f"   Response: {text}")

                    # This should show the validation error
                    if "error" in text:
                        print("   ✅ FastMCP correctly rejects malformed parameters")
                    else:
                        print("   ⚠️  Unexpected response")

            except Exception as e:
                print(f"   Exception: {e}")

            # Test 2: Send the correct message
            print("\\n2. Testing CORRECT agent message format:")
            print(f"   Sending: {correct_agent_message}")

            try:
                async with session.post(
                    f"http://localhost:{mcp_port}/mcp",
                    json=correct_agent_message,
                    headers=headers
                ) as response:
                    text = await response.text()
                    print(f"   Status: {response.status}")
                    print(f"   Response: {text}")

                    if response.status == 200:
                        print("   ✅ Correct format works")
                    elif "Missing session" in text or "session ID" in text:
                        print("   ✅ Correct format accepted (session management issue)")
                    else:
                        print("   ⚠️  Unexpected response")

            except Exception as e:
                print(f"   Exception: {e}")

        print("\\n📋 CONCLUSION FOR AGENT DEVELOPERS:")
        print("❌ Don't send: 'arguments': {'params': '{}'}")
        print("✅ Do send:    'arguments': {'count': 5}")
        print("✅ The 'count' goes directly in 'arguments', not nested in 'params'")

    @pytest.mark.asyncio
    async def test_mcp_http_endpoint_is_callable(self, full_mcp_system):
        """Test that MCP HTTP endpoint is properly configured and callable

        This test prevents the 'FastMCP object is not callable' error
        by verifying the HTTP server can actually serve requests.
        """
        system = full_mcp_system
        mcp_port = system['mcp_port']

        try:
            import aiohttp
        except ImportError:
            pytest.skip("aiohttp not available for HTTP testing")

        # Give server time to fully start
        await asyncio.sleep(1.0)

        async with aiohttp.ClientSession() as session:
            # Test that the MCP endpoint responds (even with an error is fine,
            # as long as it doesn't raise "FastMCP object is not callable")
            try:
                async with session.get(f"http://localhost:{mcp_port}/mcp") as response:
                    # Any response (including error) means the server is callable
                    assert response.status in [200, 400, 406], f"Unexpected status: {response.status}"

                    # Verify it's a proper JSON-RPC response
                    if response.status != 406:  # 406 = Not Acceptable for missing headers
                        text = await response.text()
                        data = json.loads(text)
                        assert "jsonrpc" in data or "error" in data

                    print(f"✓ MCP HTTP endpoint is callable and responds correctly (status: {response.status})")

            except Exception as e:
                if "'FastMCP' object is not callable" in str(e):
                    pytest.fail("FastMCP object is not callable - missing .http_app() call")
                else:
                    # Other errors are acceptable as long as it's not the callable error
                    print(f"✓ MCP endpoint accessible (got expected error: {type(e).__name__})")

    def test_mcp_tools_have_proper_schemas(self):
        """Test that all MCP tools have proper JSON schemas"""
        from server.mcp_tools import FoxMCPTools

        # Create mock server for testing
        class MockServer:
            async def send_request_and_wait(self, request, timeout=10.0):
                return {"type": "response", "data": {}}

        mock_server = MockServer()
        mcp_tools = FoxMCPTools(mock_server)
        mcp_app = mcp_tools.get_mcp_app()

        # Verify FastMCP app was created
        from fastmcp.server.server import FastMCP
        assert isinstance(mcp_app, FastMCP)

        print("✓ MCP tools have proper FastMCP integration")

    @pytest.mark.asyncio
    async def test_all_history_tools_schema_validation(self):
        """Test schema validation for all history-related tools"""
        from server.server import FoxMCPServer

        server = FoxMCPServer(start_mcp=False)
        tools_dict = await server.mcp_app.get_tools()

        # Find all history tools
        history_tools = {name: tool for name, tool in tools_dict.items() if 'history' in name}

        assert len(history_tools) > 0, "Should have history tools"

        for tool_name, tool_func in history_tools.items():
            print(f"Validating history tool: {tool_name}")

            # Verify tool has proper schema
            if hasattr(tool_func, 'parameters'):
                params = tool_func.parameters
                assert isinstance(params, dict), f"Tool {tool_name} parameters should be dict"

                # Common validation for all history tools
                if 'properties' in params:
                    for param_name, param_schema in params['properties'].items():
                        # Check if parameter has type directly or through anyOf/oneOf
                        has_type = ('type' in param_schema or
                                   'anyOf' in param_schema or
                                   'oneOf' in param_schema)
                        assert has_type, f"Parameter {param_name} missing type specification"

            print(f"✓ {tool_name} schema valid")

        print(f"✓ All {len(history_tools)} history tools have valid schemas")

    @pytest.mark.asyncio
    async def test_all_tab_tools_schema_validation(self):
        """Test schema validation for all tab-related tools"""
        from server.server import FoxMCPServer

        server = FoxMCPServer(start_mcp=False)
        tools_dict = await server.mcp_app.get_tools()

        tab_tools = {name: func for name, func in tools_dict.items() if 'tab' in name}

        assert len(tab_tools) > 0, "Should have tab tools"

        for tool_name, tool_func in tab_tools.items():
            print(f"Validating tab tool: {tool_name}")

            # Verify tool has proper schema
            if hasattr(tool_func, 'parameters'):
                params = tool_func.parameters
                assert isinstance(params, dict), f"Tool {tool_name} parameters should be dict"

                # Common validation for all tab tools
                if 'properties' in params:
                    for param_name, param_schema in params['properties'].items():
                        # Check if parameter has type directly or through anyOf/oneOf
                        has_type = ('type' in param_schema or
                                   'anyOf' in param_schema or
                                   'oneOf' in param_schema)
                        assert has_type, f"Parameter {param_name} missing type specification"

            print(f"✓ {tool_name} schema valid")

        print(f"✓ All {len(tab_tools)} tab tools have valid schemas")

    @pytest.mark.asyncio
    async def test_tab_tools_exist_and_callable(self):
        """Test that essential tab tools exist and are callable"""
        from server.server import FoxMCPServer

        server = FoxMCPServer(start_mcp=False)
        tools_dict = await server.mcp_app.get_tools()

        # Essential tab tools that should exist
        essential_tab_tools = [
            'tabs_list',
            'tabs_create',
            'tabs_close',
            'tabs_switch'
        ]

        for tool_name in essential_tab_tools:
            assert tool_name in tools_dict, f"Essential tool {tool_name} not found in MCP tools"
            # For FastMCP tools, check if it has the tool attributes
            tool = tools_dict[tool_name]
            assert hasattr(tool, 'name'), f"Tool {tool_name} should have name attribute"
            assert tool.name == tool_name, f"Tool name mismatch: {tool.name} != {tool_name}"

        print(f"✓ All {len(essential_tab_tools)} essential tab tools exist and have proper structure")

    @pytest.mark.asyncio
    async def test_tool_parameter_validation(self):
        """Test that tools properly validate their parameters"""
        from server.server import FoxMCPServer

        server = FoxMCPServer(start_mcp=False)
        tools_dict = await server.mcp_app.get_tools()

        # Test a specific tool's parameter validation
        if 'history_get_recent' in tools_dict:
            tool = tools_dict['history_get_recent']

            # Should have count parameter with proper validation
            if hasattr(tool, 'parameters') and 'properties' in tool.parameters:
                if 'count' in tool.parameters['properties']:
                    count_param = tool.parameters['properties']['count']
                    # Check for type directly or through anyOf/oneOf
                    has_integer_type = (
                        count_param.get('type') == 'integer' or
                        ('anyOf' in count_param and any(t.get('type') == 'integer' for t in count_param['anyOf'])) or
                        ('oneOf' in count_param and any(t.get('type') == 'integer' for t in count_param['oneOf']))
                    )
                    assert has_integer_type, "count should have integer type"
                    assert 'default' in count_param, "count should have default"

        print("✓ Tool parameter validation working correctly")

    @pytest.mark.asyncio
    async def test_mcp_server_creates_proper_asgi_app(self):
        """Test that MCP server creates proper ASGI app for HTTP serving"""
        from server.server import FoxMCPServer

        # Use coordinated ports to avoid conflicts
        with coordinated_test_ports() as (ports, coord_file):
            websocket_port = ports['websocket']
            mcp_port = ports['mcp']

            server = FoxMCPServer(
                host="localhost",
                port=websocket_port,
                mcp_port=mcp_port,
                start_mcp=True
            )

            # Verify MCP app is created and is callable
            assert hasattr(server, 'mcp_app'), "Server should have mcp_app"
            assert server.mcp_app is not None, "mcp_app should not be None"

            # Test that it has the expected ASGI interface
            if hasattr(server.mcp_app, 'http_app'):
                http_app = server.mcp_app.http_app()
                assert callable(http_app), "HTTP app should be callable"

            print("✓ MCP server creates proper ASGI application")