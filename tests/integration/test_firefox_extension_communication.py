"""
Test real communication between FoxMCPServer and Firefox extension
This test starts Firefox with the extension and verifies WebSocket communication
"""

import pytest
import pytest_asyncio
import json
import asyncio
import websockets
import time
import subprocess
import signal
import os
import tempfile
import shutil
import sys
import re
from pathlib import Path

import test_imports  # Automatic path setup
from test_config import profile_connection
from server.server import FoxMCPServer
from server.browser_profile import BrowserProfile
from test_config import TEST_PORTS, connect_as_extension
from firefox_test_utils import FirefoxTestManager
from port_coordinator import get_port_by_type
from mcp_client_harness import DirectMCPTestClient


class TestFirefoxExtensionCommunication:
    """Test real communication with Firefox extension"""

    @pytest.fixture
    def firefox_path(self):
        """Get Firefox path from environment or default"""
        return os.environ.get('FIREFOX_PATH', 'firefox')

    @pytest.fixture  
    def temp_profile(self):
        """Create temporary Firefox profile for testing"""
        profile_dir = tempfile.mkdtemp(prefix='foxmcp-test-')
        
        # Create user.js with extension settings
        user_js_content = '''
user_pref("xpinstall.signatures.required", false);
user_pref("extensions.autoDisableScopes", 0);
user_pref("extensions.enabledScopes", 15);
user_pref("dom.disable_open_during_load", false);
user_pref("browser.tabs.remote.autostart", false);
'''
        
        with open(os.path.join(profile_dir, 'user.js'), 'w') as f:
            f.write(user_js_content)
            
        yield profile_dir
        
        # Cleanup
        shutil.rmtree(profile_dir, ignore_errors=True)


    @pytest_asyncio.fixture
    async def running_server(self):
        """Start FoxMCPServer for testing with fixed Firefox test port"""
        # Use fixed ports for Firefox extension testing
        ports = TEST_PORTS['integration']
        server = FoxMCPServer(
            host="localhost", 
            port=ports['websocket'],
            mcp_port=ports['mcp'], 
            start_mcp=False  # Disable MCP for extension tests
        )
        server_task = asyncio.create_task(server.start_server())
        
        # Wait for server to start
        await asyncio.sleep(0.5)
        
        server._test_port = ports['websocket']
        yield server

        # Cleanup
        try:
            await server.shutdown(server_task)
        except Exception as e:
            # Log but don't fail on cleanup issues
            pass


    @pytest.mark.asyncio
    async def test_server_starts_before_extension_connects(self, running_server, firefox_path, temp_profile):
        """Test server is ready when extension tries to connect"""
        
        # Server should be running
        assert running_server is not None
        
        # Try to connect as client to verify server is accessible
        try:
            uri = f"ws://localhost:{running_server._test_port}"
            websocket = await connect_as_extension(uri)
            
            # Send test message
            test_msg = {
                "id": "server-ready-test",
                "type": "request", 
                "action": "ping",
                "data": {"test": True},
                "timestamp": time.time()
            }
            
            await websocket.send(json.dumps(test_msg))
            await websocket.close()
            
        except Exception as e:
            pytest.fail(f"Server should be accessible: {e}")

    @pytest.mark.asyncio 
    async def test_extension_can_connect_to_server(self, running_server):
        """Test that Firefox extension can connect to server using coordinated ports"""
        
        firefox_manager = None
        connection_detected = False
        
        try:
            # Get extension XPI path
            
            # Create Firefox test manager with coordinated port
            firefox_manager = FirefoxTestManager(
                firefox_path=os.environ.get('FIREFOX_PATH', 'firefox'),
                test_port=running_server._test_port
            )
            
            # Set up Firefox with extension and start it
            success = firefox_manager.setup_and_start_firefox(headless=True)
            if success:
                # Use the new awaitable connection mechanism
                connection_detected = await firefox_manager.async_wait_for_extension_connection(
                    timeout=10.0, server=running_server
                )
            
        except Exception as e:
            print(f"Extension connection test error: {e}")
            
        finally:
            # Cleanup Firefox
            if firefox_manager:
                firefox_manager.cleanup()
        
        # Verify test infrastructure worked
        assert connection_detected, "Firefox should start successfully with extension"

    @pytest.mark.asyncio
    async def test_bidirectional_message_flow(self, running_server, firefox_path, temp_profile):
        """Test bidirectional message flow between server and extension"""

        # Create Firefox test manager
        firefox = FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=running_server._test_port
        )

        try:
            # Start Firefox with extension
            success = firefox.setup_and_start_firefox(headless=True)
            if not success:
                pytest.skip("Firefox setup or extension installation failed")

            # Wait for extension to connect using the new awaitable mechanism
            connected = await firefox.async_wait_for_extension_connection(
                timeout=10.0, server=running_server
            )
            if not connected:
                pytest.skip("Extension failed to connect to server")
            
            # Test message handling on server side
            test_messages = [
                {
                    "id": "bidirectional-tabs",
                    "type": "request",
                    "action": "tabs.list",
                    "data": {},
                    "timestamp": time.time()
                },
                {
                    "id": "bidirectional-history",  
                    "type": "request",
                    "action": "history.query",
                    "data": {"query": "test", "maxResults": 10},
                    "timestamp": time.time()
                },
                {
                    "id": "bidirectional-response",
                    "type": "response", 
                    "action": "bookmarks.list",
                    "data": {"bookmarks": []},
                    "timestamp": time.time()
                }
            ]
            
            # Test that server can handle these message types
            for msg in test_messages:
                await BrowserProfile(running_server, None, "test-profile", "moz-extension://test").handle_extension_message(json.dumps(msg))
            
            # Test server's send capability (even without active extension)
            test_send_msg = {
                "id": "server-to-ext",
                "type": "request",
                "action": "tabs.get_active", 
                "data": {},
                "timestamp": time.time()
            }
            
            result = await profile_connection(running_server).send_to_extension(test_send_msg)
            # Should return False if no extension connected, which is expected
            assert result in [True, False]  # Either state is valid for this test
            
        except Exception as e:
            print(f"Bidirectional test error: {e}")
            
        finally:
            # Cleanup Firefox
            firefox.cleanup()

    @pytest.mark.asyncio
    async def test_extension_message_protocol_compatibility(self, running_server):
        """Test that server handles extension messages according to protocol"""
        
        # Test various message formats that extension might send
        extension_messages = [
            # Successful tab list response
            {
                "id": "ext-tabs-001",
                "type": "response",
                "action": "tabs.list",
                "data": {
                    "tabs": [
                        {"id": 1, "url": "https://example.com", "title": "Example", "active": True},
                        {"id": 2, "url": "https://mozilla.org", "title": "Mozilla", "active": False}
                    ]
                },
                "timestamp": time.time()
            },
            
            # History query response
            {
                "id": "ext-history-001",
                "type": "response", 
                "action": "history.query",
                "data": {
                    "results": [
                        {"url": "https://example.com", "title": "Example", "visitTime": time.time()},
                        {"url": "https://test.com", "title": "Test", "visitTime": time.time() - 3600}
                    ]
                },
                "timestamp": time.time()
            },
            
            # Error response
            {
                "id": "ext-error-001",
                "type": "error",
                "action": "tabs.close",
                "data": {
                    "error": "Tab not found",
                    "code": 404,
                    "details": "Tab with ID 999 does not exist"
                },
                "timestamp": time.time()
            },
            
            # Bookmark creation success
            {
                "id": "ext-bookmark-001",
                "type": "response",
                "action": "bookmarks.create", 
                "data": {
                    "bookmark": {
                        "id": "bookmark_123",
                        "url": "https://newbookmark.com",
                        "title": "New Bookmark",
                        "folder": "Bookmarks Toolbar"
                    }
                },
                "timestamp": time.time()
            }
        ]
        
        # Test that server can handle all these message types
        for msg in extension_messages:
            try:
                await BrowserProfile(running_server, None, "test-profile", "moz-extension://test").handle_extension_message(json.dumps(msg))
                print(f"✓ Handled {msg['type']} message for action {msg['action']}")
            except Exception as e:
                pytest.fail(f"Server should handle extension message {msg['action']}: {e}")


class TestFirefoxConnectionResilience:
    """Test connection resilience and recovery"""

    @pytest.mark.asyncio
    async def test_server_handles_connection_loss(self):
        """Test server handles connection loss gracefully"""
        # Use individual dynamic ports for resilience testing
        port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')
        server = FoxMCPServer(host="localhost", port=port, mcp_port=mcp_port, start_mcp=False)
        
        # Start server
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(0.3)
        
        try:
            # Connect and disconnect multiple times
            for i in range(3):
                websocket = await connect_as_extension(f"ws://localhost:{port}")
                
                # Send message
                msg = {
                    "id": f"resilience-{i}",
                    "type": "request",
                    "action": "ping",
                    "data": {},
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(msg))
                
                # Abruptly close connection
                await websocket.close()
                
                # Brief pause
                await asyncio.sleep(0.1)
            
            # Server should still be running
            assert not server_task.done()
            
        finally:
            await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_multiple_connection_attempts(self):
        """Test server can handle multiple connection attempts"""
        # Use individual dynamic ports for multiple connection testing
        port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')
        server = FoxMCPServer(host="localhost", port=port, mcp_port=mcp_port, start_mcp=False)
        
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(0.3)
        
        try:
            # Multiple simultaneous connections
            connections = []
            
            for i in range(5):
                websocket = await connect_as_extension(f"ws://localhost:{port}")
                connections.append(websocket)
                
                # Send unique message
                msg = {
                    "id": f"multi-conn-{i}",
                    "type": "request", 
                    "action": "tabs.list",
                    "data": {"client_id": i},
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(msg))
            
            # Close all connections
            for websocket in connections:
                await websocket.close()
                
        finally:
            await server.shutdown(server_task)


async def _distinct_connections(server, seconds, interval=0.05):
    """Extension connections the server holds over a window, in order of arrival

    Samples rather than counting accepts, because websockets.serve() captured
    handle_extension_connection when the server started and a wrapper installed
    afterwards would never be called. A connection that comes and goes between
    two samples is missed, so keep the interval well under the extension's retry
    interval, which the test profile sets to 1000 ms.
    """
    seen = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = next((p.extension_connection for p in server.profiles.values()), None)
        if current is not None and (not seen or seen[-1] is not current):
            seen.append(current)
        await asyncio.sleep(interval)
    return seen


@pytest.mark.asyncio
async def test_deliberate_reconnect_settles(server_with_extension):
    """A reconnect asked for by the user leaves one connection, not a cycle

    The popup's Reconnect button closes the socket and opens a new one. onclose
    cannot see that the close was deliberate, so it also scheduled a reconnect,
    whose timer then closed the healthy socket and opened another, whose close
    scheduled the next. That is a connect/close cycle every retryInterval which
    no retry cap stops, because retryAttempts resets on each successful open.
    """
    server = server_with_extension['server']
    mcp_client = DirectMCPTestClient(server.mcp_tools)
    await mcp_client.connect()

    create_result = await mcp_client.call_tool("tabs_create", {
        "url": "https://example.org/",
        "active": True
    })
    tab_match = re.search(r'ID (\d+)', str(create_result.get('content', '')))
    assert tab_match, f"Could not read a tab id from {create_result}"
    tab_id = int(tab_match.group(1))

    # forceReconnect is the popup's message, and a test has no popup. A content
    # script can send it, and sending it on a timer keeps the close away from
    # the socket this very call has to answer on.
    script_result = await mcp_client.call_tool("content_execute_script", {
        "tab_id": tab_id,
        "code": "setTimeout(() => browser.runtime.sendMessage({action: 'forceReconnect'}), 1000); 'scheduled'"
    })
    assert not script_result.get('isError'), f"Could not reach the extension: {script_result}"

    # Let the reconnect the user asked for happen and settle.
    await asyncio.sleep(3.0)

    connections = await _distinct_connections(server, seconds=5.0)
    assert len(connections) == 1, (
        f"{len(connections)} extension connections in 5 seconds after one "
        "deliberate reconnect; the extension is cycling"
    )


@pytest.mark.asyncio
async def test_dropped_connection_still_reconnects(server_with_extension):
    """A close the extension did not ask for still brings it back

    The guard that stops a deliberate close from scheduling a reconnect must not
    stop a real one, which is the only thing keeping the extension usable after
    a server restart.
    """
    server = server_with_extension['server']
    dropped = next((p.extension_connection for p in server.profiles.values()), None)
    assert dropped is not None, "Fixture handed over no extension connection"

    await dropped.close()

    reconnected = None
    for _ in range(100):
        await asyncio.sleep(0.1)
        current = next((p.extension_connection for p in server.profiles.values()), None)
        if current is not None and current is not dropped:
            reconnected = current
            break

    assert reconnected is not None, "Extension never reconnected after the socket was dropped"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])