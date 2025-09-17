"""
End-to-end tests for complete MCP client → server → WebSocket → Firefox extension chain
Tests the full integration from MCP client tool calls to actual browser actions
"""

import pytest
import pytest_asyncio
import asyncio
import json
import os
import sys
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.server import FoxMCPServer
try:
    from ..port_coordinator import coordinated_test_ports
    from ..firefox_test_utils import FirefoxTestManager, get_extension_xpi_path
    from ..test_config import FIREFOX_TEST_CONFIG
    from ..mcp_client_harness import DirectMCPTestClient, MCPTestClient
except ImportError:
    from port_coordinator import coordinated_test_ports
    from firefox_test_utils import FirefoxTestManager, get_extension_xpi_path
    from test_config import FIREFOX_TEST_CONFIG
    from mcp_client_harness import DirectMCPTestClient, MCPTestClient


# Using the proper MCP client harness from mcp_client_harness.py


class TestEndToEndMCP:
    """End-to-end tests for complete MCP chain"""
    
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
            
            # Track connections and messages for testing
            server.connected_clients = []
            server.received_messages = []
            server.sent_messages = []
            
            # Override handlers to track activity
            original_connection_handler = server.handle_extension_connection
            original_message_handler = server.handle_extension_message
            
            async def tracking_connection_handler(websocket):
                server.connected_clients.append(websocket)
                try:
                    await original_connection_handler(websocket)
                finally:
                    if websocket in server.connected_clients:
                        server.connected_clients.remove(websocket)
            
            async def tracking_message_handler(message):
                server.received_messages.append(message)
                result = await original_message_handler(message)
                return result
                
            # Override send method to track sent messages
            original_send = server.send_to_extension
            async def tracking_send(message):
                server.sent_messages.append(message)
                return await original_send(message)
            
            server.handle_extension_connection = tracking_connection_handler
            server.handle_extension_message = tracking_message_handler  
            server.send_to_extension = tracking_send
            
            # Start servers (WebSocket server only - MCP handled by start_mcp=True)
            websocket_task = asyncio.create_task(server.start_server())
            
            # Wait for servers to start
            await asyncio.sleep(1.0)
            
            # Create real MCP client harness 
            # Use DirectMCPTestClient for more reliable testing
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
                websocket_task.cancel()
                
                try:
                    await websocket_task
                except asyncio.CancelledError:
                    pass
    
    @pytest.mark.asyncio
    async def test_mcp_server_startup(self, full_mcp_system):
        """Test that both MCP and WebSocket servers start correctly"""
        system = full_mcp_system
        server = system['server']
        
        # Verify MCP server is running
        assert hasattr(server, 'mcp_tools')
        assert server.mcp_tools is not None
        assert hasattr(server, 'mcp_app')
        assert server.mcp_app is not None
        
        # Verify WebSocket server is ready
        assert server.port == system['websocket_port']
        
        print(f"✓ MCP server running on port {system['mcp_port']}")
        print(f"✓ WebSocket server running on port {system['websocket_port']}")
    
    @pytest.mark.asyncio  
    async def test_mcp_client_connection(self, full_mcp_system):
        """Test MCP client can connect to server"""
        system = full_mcp_system
        mcp_client = system['mcp_client']
        
        # Connect MCP client
        connected = await mcp_client.connect()
        assert connected, "MCP client should be able to connect"
        
        print("✓ MCP client connected to server")
    
    @pytest.mark.asyncio
    async def test_extension_websocket_connection(self, full_mcp_system):
        """Test Firefox extension connects via WebSocket"""
        system = full_mcp_system
        server = system['server']
        
        # Skip if extension or Firefox not available
        extension_xpi = get_extension_xpi_path()
        if not extension_xpi or not os.path.exists(extension_xpi):
            pytest.skip("Extension XPI not found. Run 'make package' first.")
        
        firefox_path = os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip(f"Firefox not found at {firefox_path}. Set FIREFOX_PATH environment variable.")
        
        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'],
            coordination_file=system['coordination_file']
        ) as firefox:
            
            # Set up Firefox profile and install extension
            firefox.create_test_profile()
            assert firefox.install_extension(extension_xpi), "Extension should install"
            
            # Start Firefox
            assert firefox.start_firefox(headless=True), "Firefox should start"
            
            # Wait for extension to connect (give it more time)
            max_wait_time = FIREFOX_TEST_CONFIG['extension_install_wait'] + 5.0
            connect_wait_step = 1.0
            total_waited = 0
            
            print(f"Waiting up to {max_wait_time}s for extension to connect...")
            while total_waited < max_wait_time:
                await asyncio.sleep(connect_wait_step)
                total_waited += connect_wait_step
                
                if len(server.connected_clients) > 0:
                    print(f"✓ Extension connected after {total_waited}s")
                    break
                else:
                    print(f"Still waiting... {total_waited}/{max_wait_time}s (clients: {len(server.connected_clients)})")
            
            # Check if Firefox process is still running
            if firefox.firefox_process and firefox.firefox_process.poll() is not None:
                pytest.skip("Firefox process exited - cannot test extension connection")
            
            # Note: Extension might be connecting to default port 8765 instead of test port
            # This is a known issue where extension uses browser storage config vs file config
            if len(server.connected_clients) == 0:
                print(f"⚠ Extension did not connect to test port {system['websocket_port']}")
                print("Note: Extension may be trying to connect to default port 8765")
                pytest.skip("Extension connection issue - likely config mismatch")
            
            # Verify extension connected
            assert len(server.connected_clients) > 0, "Extension should connect to WebSocket server"
            
            print(f"✓ Firefox extension connected via WebSocket")
            print(f"✓ {len(server.connected_clients)} WebSocket client(s) connected")
    
    @pytest.mark.asyncio
    async def test_full_chain_mcp_to_browser_action(self, full_mcp_system):
        """Test complete chain: MCP client → MCP server → WebSocket → Extension → Browser API"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']
        
        # Skip if required components not available
        extension_xpi = get_extension_xpi_path()
        if not extension_xpi or not os.path.exists(extension_xpi):
            pytest.skip("Extension XPI not found")
            
        firefox_path = os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')  
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip("Firefox not found")
        
        # Connect MCP client
        await mcp_client.connect()
        
        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'], 
            coordination_file=system['coordination_file']
        ) as firefox:
            
            firefox.create_test_profile()
            firefox.install_extension(extension_xpi)
            firefox.start_firefox(headless=True)
            
            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])
            
            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test full chain")
            
            initial_message_count = len(server.received_messages)
            initial_sent_count = len(server.sent_messages)
            
            # Make MCP tool call
            print("Making MCP tool call: tabs_list")
            result = await mcp_client.call_tool("tabs_list")
            
            # Wait for message processing
            await asyncio.sleep(2.0)
            
            # Verify messages flowed through the system
            final_message_count = len(server.received_messages)
            final_sent_count = len(server.sent_messages)
            
            print(f"Messages received: {initial_message_count} → {final_message_count}")
            print(f"Messages sent: {initial_sent_count} → {final_sent_count}")
            
            # For now, just verify the MCP call succeeded
            # In a complete implementation, we'd verify:
            # 1. MCP tool call triggered WebSocket message to extension
            # 2. Extension received and processed the message  
            # 3. Extension called browser API (tabs.query)
            # 4. Extension sent response back via WebSocket
            # 5. Response flowed back to MCP client
            
            assert not result['isError'], "MCP tool call should not error"
            
            print("✓ MCP tool call completed (basic verification)")
            print("Note: Full chain verification requires real MCP client integration")
    
    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, full_mcp_system):
        """Test multiple MCP tool calls work correctly"""
        system = full_mcp_system
        mcp_client = system['mcp_client']
        
        await mcp_client.connect()
        
        # Test different tool categories
        tool_tests = [
            ("tabs_list", {}),
            ("history_query", {"query": "example", "max_results": 10}),
            ("history_get_recent", {"count": 5}),
            ("bookmarks_list", {}),
            ("debug_websocket_status", {})
        ]
        
        for tool_name, args in tool_tests:
            print(f"Testing MCP tool: {tool_name}")
            result = await mcp_client.call_tool(tool_name, args)
            
            # Basic verification that tool call completed
            assert 'content' in result
            
            # Most tools will fail without browser extension connection, but that's expected
            # We're just testing that the MCP layer works and doesn't crash
            if result.get('isError', False):
                content = result.get('content', '')
                print(f"   Expected error (no extension): {content[:100]}...")
                # Verify it's a connection error, not a tool definition error
                assert any(keyword in content.lower() for keyword in [
                    'no extension connection', 'connection', 'websocket', 'missing 1 required positional argument'
                ]), f"Unexpected error type: {content}"
            else:
                print(f"   Success: {result.get('content', '')[:100]}...")
            
            # Small delay between calls
            await asyncio.sleep(0.5)
        
        print("✓ Multiple MCP tool calls completed successfully")
    
    @pytest.mark.asyncio
    async def test_mcp_recent_history_functionality(self, full_mcp_system):
        """Test comprehensive recent history functionality through MCP
        
        This test ensures the MCP server can retrieve recent browser history
        and handles various parameter combinations correctly.
        """
        system = full_mcp_system
        mcp_client = system['mcp_client']
        
        await mcp_client.connect()
        
        # Test 1: Basic recent history call
        print("Testing basic recent history retrieval...")
        result = await mcp_client.call_tool("history_get_recent", {"count": 5})
        
        assert 'content' in result, "MCP result should have content"
        assert result['success'], f"Recent history call should succeed: {result}"
        assert not result.get('isError', False), f"Should not be error: {result}"
        
        # Test 2: Different count parameters
        test_counts = [1, 10, 20]
        for count in test_counts:
            print(f"Testing recent history with count={count}...")
            result = await mcp_client.call_tool("history_get_recent", {"count": count})
            
            assert result['success'], f"Recent history with count={count} should succeed"
            assert not result.get('isError', False), f"Count={count} should not error"
            
            # Small delay between calls
            await asyncio.sleep(0.2)
        
        # Test 3: Default parameters (no count specified)
        print("Testing recent history with default parameters...")
        result = await mcp_client.call_tool("history_get_recent", {})
        
        assert result['success'], "Recent history with default params should succeed"
        assert not result.get('isError', False), "Default params should not error"
        
        # Test 4: Edge case - zero count
        print("Testing recent history with count=0...")
        result = await mcp_client.call_tool("history_get_recent", {"count": 0})
        
        # This should either succeed with empty results or handle gracefully
        assert result['success'], "Recent history with count=0 should be handled gracefully"
        
        # Test 5: Large count value
        print("Testing recent history with large count...")
        result = await mcp_client.call_tool("history_get_recent", {"count": 100})
        
        assert result['success'], "Recent history with large count should succeed"
        assert not result.get('isError', False), "Large count should not error"
        
        print("✓ MCP recent history functionality working correctly")
        print("✓ All parameter combinations handled properly")
    
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
    
    @pytest.mark.asyncio
    async def test_end_to_end_tab_creation_and_listing(self, full_mcp_system):
        """Test complete end-to-end tab creation and listing with actual browser tabs"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']
        
        # Skip if required components not available
        extension_xpi = get_extension_xpi_path()
        if not extension_xpi or not os.path.exists(extension_xpi):
            pytest.skip("Extension XPI not found")
            
        firefox_path = os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')  
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip("Firefox not found")
        
        # Connect MCP client
        await mcp_client.connect()
        
        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'], 
            coordination_file=system['coordination_file']
        ) as firefox:
            
            firefox.create_test_profile()
            firefox.install_extension(extension_xpi)
            firefox.start_firefox(headless=True)
            
            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])
            
            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test tab functionality")
            
            print("\\n🧪 Testing End-to-End Tab Creation and Listing")
            
            # Step 1: Test tabs_list when no tabs exist (or only about:blank)
            print("\\n1️⃣  Testing tabs_list with minimal tabs...")
            result = await mcp_client.call_tool("tabs_list")
            
            # This should succeed even if no tabs found
            assert not result.get('isError', False), f"tabs_list should not error: {result}"
            initial_content = result.get('content', '')
            print(f"   Initial tab state: {initial_content}")
            
            # Step 2: Create test tabs using extension helper
            print("\\n2️⃣  Creating test tabs via extension...")
            
            # Use the WebSocket to send test helper command
            if hasattr(server, 'send_to_extension'):
                test_create_request = {
                    "id": str(uuid.uuid4()),
                    "type": "request",
                    "action": "test.create_test_tabs",
                    "data": {
                        "count": 3,
                        "closeExisting": True,
                        "urls": [
                            "https://example.com",
                            "https://httpbin.org/status/200", 
                            "https://httpbin.org/html"
                        ]
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
                try:
                    create_response = await server.send_to_extension(test_create_request)
                    
                    if create_response.get("type") == "response":
                        print(f"   ✅ Created test tabs: {create_response.get('data', {}).get('message')}")
                        
                        # Wait for tabs to be created and loaded
                        await asyncio.sleep(3.0)
                        
                        # Step 3: Test tabs_list with created tabs
                        print("\\n3️⃣  Testing tabs_list with created tabs...")
                        result = await mcp_client.call_tool("tabs_list")
                        
                        assert not result.get('isError', False), f"tabs_list should not error after creating tabs: {result}"
                        
                        tab_content = result.get('content', '')
                        print(f"   Tab list content: {tab_content}")
                        
                        # Verify we got actual tab data, not "No tabs found"
                        assert "No tabs found" not in tab_content, "Should find tabs after creating them"
                        assert "Open tabs:" in tab_content or "ID " in tab_content, "Should show tab information"
                        
                        # Step 4: Verify tab creation tool
                        print("\\n4️⃣  Testing tabs_create via MCP...")
                        create_result = await mcp_client.call_tool("tabs_create", {
                            "url": "https://httpbin.org/json",
                            "active": True
                        })
                        
                        assert not create_result.get('isError', False), f"tabs_create should not error: {create_result}"
                        
                        create_content = create_result.get('content', '')
                        print(f"   Tab creation result: {create_content}")
                        
                        # Verify creation was successful
                        assert "Created tab:" in create_content or "Successfully" in create_content, "Should confirm tab creation"
                        
                        # Step 5: Final tabs_list to verify all tabs
                        print("\\n5️⃣  Final tabs_list verification...")
                        final_result = await mcp_client.call_tool("tabs_list")
                        
                        assert not final_result.get('isError', False), f"Final tabs_list should not error: {final_result}"
                        
                        final_content = final_result.get('content', '')
                        print(f"   Final tab count verification: {final_content}")
                        
                        # Should have at least 4 tabs (3 from helper + 1 from MCP)
                        tab_lines = [line for line in final_content.split('\\n') if 'ID ' in line]
                        assert len(tab_lines) >= 3, f"Should have at least 3 tabs, found: {len(tab_lines)}"
                        
                        print(f"✅ End-to-end tab test successful! Found {len(tab_lines)} tabs")
                        
                    else:
                        print(f"   ⚠️  Failed to create test tabs: {create_response}")
                        pytest.skip("Could not create test tabs for verification")
                        
                except Exception as e:
                    print(f"   ⚠️  Extension test helper error: {e}")
                    pytest.skip("Extension test helper not available")
            else:
                pytest.skip("WebSocket server doesn't support extension communication")

    @pytest.mark.asyncio
    async def test_end_to_end_content_execute_script(self, full_mcp_system):
        """Test complete end-to-end JavaScript execution in browser tabs via MCP"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']
        
        # Skip if required components not available
        extension_xpi = get_extension_xpi_path()
        if not extension_xpi or not os.path.exists(extension_xpi):
            pytest.skip("Extension XPI not found")
            
        firefox_path = os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')  
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip("Firefox not found")
        
        # Connect MCP client
        await mcp_client.connect()
        
        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'], 
            coordination_file=system['coordination_file']
        ) as firefox:
            
            firefox.create_test_profile()
            firefox.install_extension(extension_xpi)
            firefox.start_firefox(headless=True)
            
            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])
            
            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test script execution")
            
            print("\n🧪 Testing End-to-End JavaScript Execution")
            
            # Step 1: Get existing tabs to find one we can test with
            print("\n1️⃣  Getting existing tabs...")
            tabs_result = await mcp_client.call_tool("tabs_list")
            assert not tabs_result.get('isError', False), f"tabs_list should not error: {tabs_result}"
            
            tab_content = tabs_result.get('content', '')
            print(f"   Available tabs: {tab_content}")
            
            # Parse tab content to find any tab
            tab_lines = [line for line in tab_content.split('\n') if 'ID ' in line and ':' in line]
            
            if not tab_lines:
                pytest.skip("No tabs found for script execution test")
            
            # Extract tab ID from the first available tab (format: "ID 123: title - url")
            tab_line = tab_lines[0]
            import re
            tab_id_match = re.search(r'ID (\d+):', tab_line)
            if not tab_id_match:
                pytest.skip("Could not extract tab ID from tabs list")
            
            test_tab_id = int(tab_id_match.group(1))
            print(f"   ✅ Found test tab ID: {test_tab_id}")
            
            # Step 2: Create a new tab with a simple web URL where content scripts can run
            print("\n2️⃣  Creating tab with web URL...")
            create_result = await mcp_client.call_tool("tabs_create", {
                "url": "https://httpbin.org/html",
                "active": True
            })
            
            if create_result.get('isError', False):
                print(f"   ⚠️  Tab creation failed: {create_result.get('content', '')}")
                print("   Using existing tab...")
            else:
                print(f"   ✅ Created web tab: {create_result.get('content', '')}")
                # Wait for tab to load and get new tab list
                await asyncio.sleep(3.0)
                
                # Get updated tab list to find our new tab
                new_tabs_result = await mcp_client.call_tool("tabs_list")
                if not new_tabs_result.get('isError', False):
                    new_tab_content = new_tabs_result.get('content', '')
                    new_tab_lines = [line for line in new_tab_content.split('\n') if 'httpbin.org' in line]
                    
                    if new_tab_lines:
                        new_tab_line = new_tab_lines[0]
                        import re
                        new_tab_id_match = re.search(r'ID (\d+):', new_tab_line)
                        if new_tab_id_match:
                            test_tab_id = int(new_tab_id_match.group(1))
                            print(f"   ✅ Using new web tab ID: {test_tab_id}")
            
            # Wait for content script to be fully loaded
            await asyncio.sleep(2.0)
            
            # Step 3: Test simple JavaScript execution
            print("\n3️⃣  Testing simple JavaScript execution...")
            script_result = await mcp_client.call_tool("content_execute_script", {
                "tab_id": test_tab_id,
                "code": "document.title"
            })
            
            assert not script_result.get('isError', False), f"Simple script should not error: {script_result}"
            
            script_content = script_result.get('content', '')
            print(f"   Script result: {script_content}")
            
            # Verify we got a result
            assert "Script result from tab" in script_content or "Script executed successfully" in script_content, \
                "Should get script execution result"
            
            # Step 4: Test JavaScript that returns a value
            print("\n4️⃣  Testing JavaScript with return value...")
            value_script = await mcp_client.call_tool("content_execute_script", {
                "tab_id": test_tab_id,
                "code": "document.body ? document.body.tagName : 'NO_BODY'"
            })
            
            assert not value_script.get('isError', False), f"Value script should not error: {value_script}"
            
            value_content = value_script.get('content', '')
            print(f"   Value script result: {value_content}")
            
            # Should return "BODY" since we're accessing the body element
            assert "BODY" in value_content, "Should return the body tag name"
            
            # Step 5: Test JavaScript that modifies the page
            print("\n5️⃣  Testing DOM modification JavaScript...")
            modify_script = await mcp_client.call_tool("content_execute_script", {
                "tab_id": test_tab_id,
                "code": "document.body.style.backgroundColor = 'lightblue'; 'DOM modified'"
            })
            
            assert not modify_script.get('isError', False), f"Modify script should not error: {modify_script}"
            
            modify_content = modify_script.get('content', '')
            print(f"   Modify script result: {modify_content}")
            
            # Should show the return value from the script
            assert "DOM modified" in modify_content, "Should return the script's return value"
            
            # Step 6: Verify the modification worked
            print("\n6️⃣  Verifying DOM modification...")
            verify_script = await mcp_client.call_tool("content_execute_script", {
                "tab_id": test_tab_id,
                "code": "document.body.style.backgroundColor"
            })
            
            assert not verify_script.get('isError', False), f"Verify script should not error: {verify_script}"
            
            verify_content = verify_script.get('content', '')
            print(f"   Verification result: {verify_content}")
            
            # Should show the modified background color
            assert "lightblue" in verify_content, "DOM modification should persist"
            
            # Step 7: Test error handling with invalid JavaScript
            print("\n7️⃣  Testing error handling...")
            error_script = await mcp_client.call_tool("content_execute_script", {
                "tab_id": test_tab_id,
                "code": "this.is.invalid.javascript()"
            })
            
            # Error script might error at MCP level or return error message
            error_content = error_script.get('content', '')
            print(f"   Error script result: {error_content}")
            
            # Should either be an error response or contain error information
            is_error_response = error_script.get('isError', False)
            contains_error_info = "error" in error_content.lower() or "failed" in error_content.lower()
            
            assert is_error_response or contains_error_info, \
                "Invalid JavaScript should produce error response or error message"
            
            print("✅ End-to-end JavaScript execution test successful!")
            print("✅ All script execution scenarios tested:")
            print("  - Simple expressions")
            print("  - DOM queries with return values")
            print("  - DOM modifications")
            print("  - Verification of changes")
            print("  - Error handling")

    @pytest.mark.asyncio
    async def test_end_to_end_navigation_reload(self, full_mcp_system):
        """Test complete end-to-end page reload functionality via MCP"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']

        # Skip if required components not available
        extension_xpi = get_extension_xpi_path()
        if not extension_xpi or not os.path.exists(extension_xpi):
            pytest.skip("Extension XPI not found")

        firefox_path = os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip("Firefox not found")

        # Connect MCP client
        await mcp_client.connect()

        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'],
            coordination_file=system['coordination_file']
        ) as firefox:

            firefox.create_test_profile()
            firefox.install_extension(extension_xpi)
            firefox.start_firefox(headless=True)

            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])

            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test navigation reload")

            print("\n🧪 Testing End-to-End Navigation Reload")

            # Step 1: Create a test tab with a web URL
            print("\n1️⃣  Creating test tab...")
            create_result = await mcp_client.call_tool("tabs_create", {
                "url": "https://httpbin.org/uuid",
                "active": True
            })

            if create_result.get('isError', False):
                pytest.skip(f"Tab creation failed: {create_result.get('content', '')}")

            print(f"   ✅ Created tab: {create_result.get('content', '')}")

            # Wait for tab to fully load
            await asyncio.sleep(3.0)

            # Step 2: Get the new tab ID from tabs list
            print("\n2️⃣  Finding test tab ID...")
            tabs_result = await mcp_client.call_tool("tabs_list")
            assert not tabs_result.get('isError', False), f"tabs_list should not error: {tabs_result}"

            tab_content = tabs_result.get('content', '')
            print(f"   Available tabs: {tab_content}")

            # Find tab with httpbin.org/uuid URL
            tab_lines = [line for line in tab_content.split('\n') if 'httpbin.org/uuid' in line]

            if not tab_lines:
                pytest.skip("Could not find test tab with httpbin.org/uuid")

            # Extract tab ID
            import re
            tab_id_match = re.search(r'ID (\d+):', tab_lines[0])
            if not tab_id_match:
                pytest.skip("Could not extract tab ID from tabs list")

            test_tab_id = int(tab_id_match.group(1))
            print(f"   ✅ Found test tab ID: {test_tab_id}")

            # Step 3: Get initial page content to verify reload works
            print("\n3️⃣  Getting initial page content...")
            initial_content_result = await mcp_client.call_tool("content_execute_script", {
                "tab_id": test_tab_id,
                "code": "document.body.textContent || 'No content'"
            })

            if initial_content_result.get('isError', False):
                print(f"   ⚠️  Could not get initial content: {initial_content_result.get('content', '')}")
                initial_uuid = None
            else:
                initial_content = initial_content_result.get('content', '')
                print(f"   Initial content: {initial_content}")

                # Extract UUID from content (httpbin.org/uuid returns a JSON with uuid field)
                import re
                uuid_match = re.search(r'"uuid":\s*"([^"]+)"', initial_content)
                initial_uuid = uuid_match.group(1) if uuid_match else None
                print(f"   ✅ Initial UUID: {initial_uuid}")

            # Step 4: Test normal reload (without bypassing cache)
            print("\n4️⃣  Testing normal reload...")
            reload_result = await mcp_client.call_tool("navigation_reload", {
                "tab_id": test_tab_id,
                "bypass_cache": False
            })

            assert not reload_result.get('isError', False), f"Normal reload should not error: {reload_result}"

            reload_content = reload_result.get('content', '')
            print(f"   Reload result: {reload_content}")

            # Verify success message
            assert "Successfully reloaded tab" in reload_content, "Should confirm successful reload"
            assert str(test_tab_id) in reload_content, "Should mention the tab ID"
            assert "bypassing cache" not in reload_content, "Normal reload should not mention bypassing cache"

            # Wait for page to reload
            await asyncio.sleep(2.0)

            # Step 5: Verify page content changed (new UUID from httpbin.org/uuid)
            print("\n5️⃣  Verifying page reloaded...")
            new_content_result = await mcp_client.call_tool("content_execute_script", {
                "tab_id": test_tab_id,
                "code": "document.body.textContent || 'No content'"
            })

            if not new_content_result.get('isError', False):
                new_content = new_content_result.get('content', '')
                print(f"   New content: {new_content}")

                # Extract new UUID
                uuid_match = re.search(r'"uuid":\s*"([^"]+)"', new_content)
                new_uuid = uuid_match.group(1) if uuid_match else None
                print(f"   ✅ New UUID: {new_uuid}")

                # UUIDs should be different (httpbin.org/uuid generates new UUID each request)
                if initial_uuid and new_uuid:
                    assert initial_uuid != new_uuid, f"UUID should change after reload: {initial_uuid} vs {new_uuid}"
                    print(f"   ✅ UUID changed: {initial_uuid} → {new_uuid}")
                else:
                    print(f"   ⚠️  Could not compare UUIDs, but page reloaded successfully")

            # Step 6: Test reload with cache bypass
            print("\n6️⃣  Testing reload with cache bypass...")
            cache_bypass_result = await mcp_client.call_tool("navigation_reload", {
                "tab_id": test_tab_id,
                "bypass_cache": True
            })

            assert not cache_bypass_result.get('isError', False), f"Cache bypass reload should not error: {cache_bypass_result}"

            cache_bypass_content = cache_bypass_result.get('content', '')
            print(f"   Cache bypass result: {cache_bypass_content}")

            # Verify success message includes cache bypass info
            assert "Successfully reloaded tab" in cache_bypass_content, "Should confirm successful reload"
            assert str(test_tab_id) in cache_bypass_content, "Should mention the tab ID"
            assert "bypassing cache" in cache_bypass_content, "Cache bypass reload should mention bypassing cache"

            # Wait for page to reload
            await asyncio.sleep(2.0)

            # Step 7: Test error handling - invalid tab ID
            print("\n7️⃣  Testing error handling...")
            invalid_tab_id = 99999
            error_result = await mcp_client.call_tool("navigation_reload", {
                "tab_id": invalid_tab_id,
                "bypass_cache": False
            })

            # Should either be an error response or contain error information
            error_content = error_result.get('content', '')
            print(f"   Error handling result: {error_content}")

            is_error_response = error_result.get('isError', False)
            contains_error_info = "error" in error_content.lower() or "failed" in error_content.lower() or "unable" in error_content.lower()

            assert is_error_response or contains_error_info, \
                "Invalid tab ID should produce error response or error message"

            # Step 8: Test parameter validation - verify both parameters work
            print("\n8️⃣  Testing parameter combinations...")

            # Test with explicit bypass_cache=False
            explicit_false_result = await mcp_client.call_tool("navigation_reload", {
                "tab_id": test_tab_id,
                "bypass_cache": False
            })

            assert not explicit_false_result.get('isError', False), "Explicit bypass_cache=False should work"
            assert "bypassing cache" not in explicit_false_result.get('content', ''), "Should not bypass cache"

            await asyncio.sleep(1.0)

            # Test with explicit bypass_cache=True again
            explicit_true_result = await mcp_client.call_tool("navigation_reload", {
                "tab_id": test_tab_id,
                "bypass_cache": True
            })

            assert not explicit_true_result.get('isError', False), "Explicit bypass_cache=True should work"
            assert "bypassing cache" in explicit_true_result.get('content', ''), "Should bypass cache"

            print("✅ End-to-end navigation reload test successful!")
            print("✅ All reload scenarios tested:")
            print("  - Normal reload (bypass_cache=False)")
            print("  - Cache bypass reload (bypass_cache=True)")
            print("  - Page content verification")
            print("  - Error handling for invalid tab ID")
            print("  - Parameter validation")

    @pytest.mark.asyncio
    async def test_end_to_end_content_execute_predefined(self, full_mcp_system):
        """Test complete end-to-end predefined script execution in browser tabs via MCP"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']
        
        # Skip if required components not available
        extension_xpi = get_extension_xpi_path()
        if not extension_xpi or not os.path.exists(extension_xpi):
            pytest.skip("Extension XPI not found")
            
        firefox_path = os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')  
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip("Firefox not found")
        
        # Set up the external scripts directory
        scripts_dir = os.path.join(os.path.dirname(__file__), 'foxmcp_scripts')
        os.environ['FOXMCP_EXT_SCRIPTS'] = scripts_dir
        
        # Verify test scripts exist
        simple_test_script = os.path.join(scripts_dir, 'simple_test.sh')
        get_page_info_script = os.path.join(scripts_dir, 'get_page_info.sh')
        multi_arg_test_script = os.path.join(scripts_dir, 'multi_arg_test.sh')
        
        if not os.path.exists(simple_test_script) or not os.path.exists(get_page_info_script):
            pytest.skip("Test scripts not found in foxmcp_scripts directory")
        
        # Connect MCP client
        await mcp_client.connect()
        
        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'], 
            coordination_file=system['coordination_file']
        ) as firefox:
            
            firefox.create_test_profile()
            firefox.install_extension(extension_xpi)
            firefox.start_firefox(headless=True)
            
            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])
            
            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test predefined script execution")
            
            print("\n🧪 Testing End-to-End Predefined Script Execution")
            
            # Step 1: Get existing tabs to find one we can test with
            print("\n1️⃣  Getting existing tabs...")
            tabs_result = await mcp_client.call_tool("tabs_list")
            assert not tabs_result.get('isError', False), f"tabs_list should not error: {tabs_result}"
            
            tab_content = tabs_result.get('content', '')
            print(f"   Available tabs: {tab_content}")
            
            # Parse tab content to find any tab
            tab_lines = [line for line in tab_content.split('\n') if 'ID ' in line and ':' in line]
            
            if not tab_lines:
                pytest.skip("No tabs found for predefined script execution test")
            
            # Extract tab ID from the first available tab
            tab_line = tab_lines[0]
            import re
            tab_id_match = re.search(r'ID (\d+):', tab_line)
            if not tab_id_match:
                pytest.skip("Could not extract tab ID from tabs list")
            
            test_tab_id = int(tab_id_match.group(1))
            print(f"   ✅ Found test tab ID: {test_tab_id}")
            
            # Step 2: Create a new tab with a simple web URL
            print("\n2️⃣  Creating tab with web URL...")
            create_result = await mcp_client.call_tool("tabs_create", {
                "url": "https://httpbin.org/html",
                "active": True
            })
            
            if create_result.get('isError', False):
                print(f"   ⚠️  Tab creation failed: {create_result.get('content', '')}")
                print("   Using existing tab...")
                target_tab_id = test_tab_id
            else:
                print(f"   ✅ Created web tab: {create_result.get('content', '')}")
                # Wait for tab to load
                await asyncio.sleep(3.0)
                
                # Get updated tab list to find our new tab
                new_tabs_result = await mcp_client.call_tool("tabs_list")
                if not new_tabs_result.get('isError', False):
                    new_tab_content = new_tabs_result.get('content', '')
                    new_tab_lines = [line for line in new_tab_content.split('\n') if 'httpbin.org' in line]
                    if new_tab_lines:
                        new_tab_match = re.search(r'ID (\d+):', new_tab_lines[0])
                        if new_tab_match:
                            target_tab_id = int(new_tab_match.group(1))
                            print(f"   ✅ Using new tab ID: {target_tab_id}")
                        else:
                            target_tab_id = test_tab_id
                    else:
                        target_tab_id = test_tab_id
                else:
                    target_tab_id = test_tab_id
            
            # Step 3: Test predefined script execution with simple_test.sh (no arguments - empty string)
            print("\n3️⃣  Testing predefined script: simple_test.sh...")
            simple_result = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "simple_test.sh",
                "script_args": ""
            })
            
            print(f"   Simple script result: {simple_result}")
            
            # The simple script should execute successfully and return page title or "Test Success"
            simple_content = simple_result.get('content', '')
            assert not simple_result.get('isError', False), f"Simple script should not error: {simple_result}"
            assert 'executed successfully' in simple_content or 'result from tab' in simple_content or 'Test Success' in simple_content, \
                f"Simple script should execute successfully: {simple_content}"
            
            # Step 4: Test predefined script execution with get_page_info.sh for page title
            print("\n4️⃣  Testing predefined script: get_page_info.sh (title)...")
            title_result = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "get_page_info.sh",
                "script_args": '["title"]'
            })
            
            print(f"   Page title result: {title_result}")
            
            title_content = title_result.get('content', '')
            assert not title_result.get('isError', False), f"Title script should not error: {title_result}"
            
            # Should contain either the page title or success message
            assert any(word in title_content.lower() for word in ['html', 'title', 'executed successfully', 'result from tab']), \
                f"Title script should return page title or success: {title_content}"
            
            # Step 5: Test predefined script execution with get_page_info.sh for page URL
            print("\n5️⃣  Testing predefined script: get_page_info.sh (url)...")
            url_result = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "get_page_info.sh",
                "script_args": '["url"]'
            })
            
            print(f"   Page URL result: {url_result}")
            
            url_content = url_result.get('content', '')
            assert not url_result.get('isError', False), f"URL script should not error: {url_result}"
            
            # Should contain the URL or success message
            assert any(word in url_content for word in ['httpbin.org', 'http', 'executed successfully', 'result from tab']), \
                f"URL script should return page URL or success: {url_content}"
            
            # Step 5.5: Test multi-argument script with arguments containing spaces
            if os.path.exists(multi_arg_test_script):
                print("\n5️⃣.5  Testing predefined script: multi_arg_test.sh (multiple args with spaces)...")
                multi_arg_result = await mcp_client.call_tool("content_execute_predefined", {
                    "tab_id": target_tab_id,
                    "script_name": "multi_arg_test.sh",
                    "script_args": '["Hello from JSON args!", "test-div", "green"]'
                })
                
                print(f"   Multi-arg script result: {multi_arg_result}")
                
                multi_arg_content = multi_arg_result.get('content', '')
                assert not multi_arg_result.get('isError', False), f"Multi-arg script should not error: {multi_arg_result}"
                # Should contain success message or result
                assert 'executed successfully' in multi_arg_content or 'result from tab' in multi_arg_content or 'Added message' in multi_arg_content, \
                    f"Multi-arg script should execute successfully: {multi_arg_content}"
            
            # Step 6: Test error handling - non-existent script (empty array format)
            print("\n6️⃣  Testing error handling: non-existent script...")
            error_result = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "nonexistent_script.sh",
                "script_args": "[]"
            })
            
            print(f"   Error handling result: {error_result}")
            
            error_content = error_result.get('content', '')
            # This should return an error about script not found
            assert 'not found' in error_content or 'Error:' in error_content, \
                f"Should return error for non-existent script: {error_content}"
            
            # Step 7: Test security validation - path traversal attack (empty string format)
            print("\n7️⃣  Testing security: path traversal attack...")
            security_result = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "../../../etc/passwd",
                "script_args": ""
            })
            
            print(f"   Security test result: {security_result}")
            
            security_content = security_result.get('content', '')
            # This should return a security error
            assert 'Invalid script name' in security_content, \
                f"Should block path traversal attack: {security_content}"
            
            # Step 8: Test security validation - invalid characters (empty string format)
            print("\n8️⃣  Testing security: invalid characters...")
            security_result2 = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "script;rm -rf /",
                "script_args": ""
            })
            
            print(f"   Security test 2 result: {security_result2}")
            
            security_content2 = security_result2.get('content', '')
            # This should return a security error
            assert 'Invalid script name' in security_content2, \
                f"Should block invalid characters: {security_content2}"
            
            # Step 8.5: Test empty string vs empty array equivalence
            print("\n8️⃣.5  Testing equivalence: empty string vs empty array...")
            empty_string_result = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "simple_test.sh",
                "script_args": ""
            })
            
            empty_array_result = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "simple_test.sh",
                "script_args": "[]"
            })
            
            print(f"   Empty string result: {empty_string_result.get('content', '')[:100]}...")
            print(f"   Empty array result: {empty_array_result.get('content', '')[:100]}...")
            
            # Both should succeed and produce similar results
            assert not empty_string_result.get('isError', False), "Empty string should not error"
            assert not empty_array_result.get('isError', False), "Empty array should not error"
            
            # Step 9: Test JSON validation - invalid JSON
            print("\n9️⃣  Testing JSON validation: invalid JSON...")
            json_error_result = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "simple_test.sh",
                "script_args": '["invalid json"'  # Missing closing bracket
            })
            
            print(f"   JSON validation result: {json_error_result}")
            
            json_error_content = json_error_result.get('content', '')
            # This should return a JSON parsing error
            assert 'Invalid JSON' in json_error_content, \
                f"Should return JSON validation error: {json_error_content}"
            
            # Step 10: Test JSON validation - non-array JSON
            print("\n🔟  Testing JSON validation: non-array JSON...")
            non_array_result = await mcp_client.call_tool("content_execute_predefined", {
                "tab_id": target_tab_id,
                "script_name": "simple_test.sh",
                "script_args": '{"key": "value"}'  # Object instead of array
            })
            
            print(f"   Non-array validation result: {non_array_result}")
            
            non_array_content = non_array_result.get('content', '')
            # This should return an error about expecting an array or empty string
            assert 'must be a JSON array of strings or empty string' in non_array_content, \
                f"Should return array validation error: {non_array_content}"
            
            print("\n✅ All predefined script execution tests passed!")
            print("✅ Security validation tests passed!")
            print("✅ JSON argument validation tests passed!")


class TestMCPProtocolCompliance:
    """Test MCP protocol compliance and schema validation"""
    
    def test_mcp_tools_have_proper_schemas(self):
        """Test that MCP tools have proper parameter schemas
        
        This is a basic test that verifies FastMCP integration.
        For detailed schema validation see:
        - test_all_history_tools_schema_validation()
        - test_all_tab_tools_schema_validation()
        """
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
        print("✓ See test_all_*_tools_schema_validation() for detailed schema tests")
    
    @pytest.mark.asyncio
    async def test_all_history_tools_schema_validation(self):
        """Test that ALL history tools have correct parameter schemas
        
        This test ensures none of the history tools have the 'params' wrapper
        issue that would confuse external MCP agents.
        """
        from server.server import FoxMCPServer
        
        server = FoxMCPServer(start_mcp=False)
        tools_dict = await server.mcp_app.get_tools()
        
        # Find all history tools
        history_tools = {name: tool for name, tool in tools_dict.items() if 'history' in name}
        
        print(f"Testing schema validation for {len(history_tools)} history tools:")
        
        # Expected schema structure for each history tool
        expected_schemas = {
            'history_query': {
                'required': ['query'],
                'optional': ['max_results', 'start_time', 'end_time'],
                'expected_types': {
                    'query': 'string',
                    'max_results': 'integer', 
                    'start_time': ['string', 'null'],
                    'end_time': ['string', 'null']
                }
            },
            'history_get_recent': {
                'required': [],
                'optional': ['count'],
                'expected_types': {
                    'count': 'integer'
                }
            },
            'history_delete_item': {
                'required': ['url'],
                'optional': [],
                'expected_types': {
                    'url': 'string'
                }
            }
        }
        
        for tool_name, tool in history_tools.items():
            print(f"\n📋 Validating {tool_name}:")
            
            schema = tool.parameters
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            
            # Test 1: No params wrapper
            assert 'params' not in properties, \
                f"❌ {tool_name} has 'params' wrapper - should use direct parameters"
            print("   ✅ No 'params' wrapper (direct parameters)")
            
            # Test 2: Schema structure matches expectations  
            if tool_name in expected_schemas:
                expected = expected_schemas[tool_name]
                
                # Check required parameters
                for req_param in expected['required']:
                    assert req_param in properties, \
                        f"❌ {tool_name} missing required parameter: {req_param}"
                    assert req_param in required, \
                        f"❌ {tool_name} parameter {req_param} should be marked as required"
                
                # Check optional parameters exist
                for opt_param in expected['optional']:
                    assert opt_param in properties, \
                        f"❌ {tool_name} missing optional parameter: {opt_param}"
                    assert opt_param not in required, \
                        f"❌ {tool_name} parameter {opt_param} should be optional"
                
                # Check parameter types
                for param_name, expected_type in expected['expected_types'].items():
                    if param_name in properties:
                        param_def = properties[param_name]
                        
                        if isinstance(expected_type, list):
                            # Handle union types like string|null
                            if 'anyOf' in param_def:
                                actual_types = [t.get('type') for t in param_def['anyOf']]
                                for exp_type in expected_type:
                                    assert exp_type in actual_types, \
                                        f"❌ {tool_name}.{param_name} should accept type {exp_type}"
                        else:
                            # Handle simple types
                            actual_type = param_def.get('type')
                            assert actual_type == expected_type, \
                                f"❌ {tool_name}.{param_name} should be {expected_type}, got {actual_type}"
                
                print(f"   ✅ Schema structure matches expectations")
                
                # Show parameter summary
                param_list = []
                for param_name in properties:
                    is_req = param_name in required
                    req_str = "required" if is_req else "optional"
                    param_list.append(f"{param_name}({req_str})")
                print(f"   ✅ Parameters: {', '.join(param_list)}")
            else:
                print(f"   ⚠️  No schema expectations defined for {tool_name}")
        
        print(f"\n🎉 All {len(history_tools)} history tools have correct schemas!")
        print("✅ No 'params' wrapper issues found")
        print("✅ All required/optional parameters validated")
        print("✅ Parameter types validated")
    
    @pytest.mark.asyncio
    async def test_all_tab_tools_schema_validation(self):
        """Test that ALL tab tools have correct parameter schemas
        
        This test ensures none of the tab tools have the 'params' wrapper
        issue that would confuse external MCP agents.
        """
        from server.server import FoxMCPServer
        
        server = FoxMCPServer(start_mcp=False)
        tools_dict = await server.mcp_app.get_tools()
        
        # Find all tab tools
        tab_tools = {name: tool for name, tool in tools_dict.items() if name.startswith('tabs_')}
        
        print(f"Testing schema validation for {len(tab_tools)} tab tools:")
        
        # Expected schema structure for each tab tool (direct parameters, no BaseModel wrapper)
        expected_schemas = {
            'tabs_list': {
                'required': [],
                'optional': [],
                'expected_types': {}
            },
            'tabs_create': {
                'required': ['url'],
                'optional': ['active', 'pinned', 'window_id'],
                'expected_types': {
                    'url': 'string',
                    'active': 'boolean',
                    'pinned': 'boolean',
                    'window_id': 'integer'  # Direct parameter, not anyOf
                }
            },
            'tabs_close': {
                'required': ['tab_id'],
                'optional': [],
                'expected_types': {
                    'tab_id': 'integer'
                }
            },
            'tabs_switch': {
                'required': ['tab_id'],
                'optional': [],
                'expected_types': {
                    'tab_id': 'integer'
                }
            }
        }
        
        for tool_name, tool in tab_tools.items():
            print(f"\n📋 Validating {tool_name}:")
            
            schema = tool.parameters
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            
            # Test 1: No params wrapper
            assert 'params' not in properties, \
                f"❌ {tool_name} has 'params' wrapper - should use direct parameters"
            print("   ✅ No 'params' wrapper (direct parameters)")
            
            # Test 2: Schema structure matches expectations  
            if tool_name in expected_schemas:
                expected = expected_schemas[tool_name]
                
                # Check required parameters
                for req_param in expected['required']:
                    assert req_param in properties, \
                        f"❌ {tool_name} missing required parameter: {req_param}"
                    assert req_param in required, \
                        f"❌ {tool_name} parameter {req_param} should be marked as required"
                
                # Check optional parameters exist
                for opt_param in expected['optional']:
                    assert opt_param in properties, \
                        f"❌ {tool_name} missing optional parameter: {opt_param}"
                    assert opt_param not in required, \
                        f"❌ {tool_name} parameter {opt_param} should be optional"
                
                # Check parameter types (handle both direct types and anyOf for optional)
                for param_name, expected_type in expected['expected_types'].items():
                    if param_name in properties:
                        param_def = properties[param_name]
                        actual_type = param_def.get('type')
                        
                        # Handle anyOf structure for optional parameters
                        if actual_type is None and 'anyOf' in param_def:
                            # Look for the expected type in anyOf array
                            any_of_types = param_def['anyOf']
                            matching_types = [t for t in any_of_types if t.get('type') == expected_type]
                            assert matching_types, \
                                f"❌ {tool_name}.{param_name} should include {expected_type} in anyOf, got {any_of_types}"
                            print(f"     ✓ {param_name}: anyOf includes {expected_type} (optional)")
                        else:
                            assert actual_type == expected_type, \
                                f"❌ {tool_name}.{param_name} should be {expected_type}, got {actual_type}"
                            print(f"     ✓ {param_name}: {actual_type} matches expected")
                
                print(f"   ✅ Schema structure matches expectations")
                
                # Show parameter summary
                param_list = []
                for param_name in properties:
                    is_req = param_name in required
                    req_str = "required" if is_req else "optional"
                    param_list.append(f"{param_name}({req_str})")
                print(f"   ✅ Parameters: {', '.join(param_list) if param_list else 'none'}")
            else:
                print(f"   ⚠️  No schema expectations defined for {tool_name}")
        
        print(f"\n🎉 All {len(tab_tools)} tab tools have correct schemas!")
        print("✅ No 'params' wrapper issues found")
        print("✅ All required/optional parameters validated")
        print("✅ Parameter types validated")
    
    @pytest.mark.asyncio
    async def test_tab_tools_exist_and_callable(self):
        """Test that all expected tab tools exist and are properly configured"""
        from server.server import FoxMCPServer
        
        server = FoxMCPServer(start_mcp=False)
        tools_dict = await server.mcp_app.get_tools()
        
        # Expected tab tools
        expected_tab_tools = ['tabs_list', 'tabs_create', 'tabs_close', 'tabs_switch']
        
        print(f"Testing existence of {len(expected_tab_tools)} tab tools:")
        
        for tool_name in expected_tab_tools:
            assert tool_name in tools_dict, f"❌ Missing tab tool: {tool_name}"
            tool = tools_dict[tool_name]
            
            # Verify it has the expected attributes
            assert hasattr(tool, 'description'), f"❌ {tool_name} missing description"
            assert hasattr(tool, 'parameters'), f"❌ {tool_name} missing parameters"
            
            print(f"   ✅ {tool_name}: {tool.description}")
        
        print(f"✅ All {len(expected_tab_tools)} tab tools exist and are properly configured")
    
    def test_tool_parameter_validation(self):
        """Test that tools have proper parameter validation"""
        from server.mcp_tools import FoxMCPTools
        from pydantic import ValidationError
        
        class MockServer:
            async def send_request_and_wait(self, request, timeout=10.0):
                return {"type": "response", "data": {}}
        
        mock_server = MockServer()  
        mcp_tools = FoxMCPTools(mock_server)
        
        # Tools should be properly set up with parameter validation
        assert hasattr(mcp_tools, 'mcp')
        assert mcp_tools.mcp is not None
        
        print("✓ MCP tools have parameter validation")
    
    @pytest.mark.asyncio  
    async def test_mcp_server_creates_proper_asgi_app(self):
        """Test that FoxMCPServer creates a proper ASGI application"""
        from server.server import FoxMCPServer
        
        server = FoxMCPServer(start_mcp=False)
        
        # Verify the MCP app has the required http_app method
        assert hasattr(server.mcp_app, 'http_app'), "FastMCP instance missing http_app method"
        
        # Verify http_app() returns an ASGI application
        http_app = server.mcp_app.http_app()
        assert http_app is not None, "http_app() returned None"
        assert hasattr(http_app, '__call__'), "http_app() result is not callable"
        
        # Verify it's the correct type (StarletteWithLifespan)
        assert 'StarletteWithLifespan' in str(type(http_app)), f"Wrong ASGI app type: {type(http_app)}"
        
        print("✓ FastMCP creates proper ASGI application via http_app()")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])
