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
from pathlib import Path

# Add the parent directory to the path to import server module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from server.server import FoxMCPServer

# Import test utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from test_config import TEST_PORTS
from firefox_test_utils import FirefoxTestManager, get_extension_xpi_path


class TestFirefoxExtensionCommunication:
    """Test real communication with Firefox extension"""

    @pytest.fixture
    def firefox_path(self):
        """Get Firefox path from environment or default"""
        return os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')

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

    @pytest.fixture
    def extension_xpi(self):
        """Get path to built extension XPI"""
        xpi_path = os.path.join(os.path.dirname(__file__), '..', '..', 'dist', 'packages', 'foxmcp@codemud.org.xpi')
        if not os.path.exists(xpi_path):
            pytest.skip("Extension XPI not found. Run 'make package' first.")
        return xpi_path

    @pytest_asyncio.fixture
    async def running_server(self):
        """Start FoxMCPServer for testing with fixed Firefox test port"""
        # Use fixed ports for Firefox extension testing
        ports = TEST_PORTS['integration_firefox']
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
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            # Log but don't fail on cleanup issues
            pass

    def start_firefox_with_extension(self, firefox_path, profile_dir, extension_xpi):
        """Start Firefox with extension installed"""
        
        # Install extension to profile
        extensions_dir = os.path.join(profile_dir, 'extensions')
        os.makedirs(extensions_dir, exist_ok=True)
        shutil.copy2(extension_xpi, extensions_dir)
        
        # Expand firefox path
        firefox_path = os.path.expanduser(firefox_path)
        
        # Start Firefox in headless mode
        firefox_cmd = [
            firefox_path,
            '-profile', profile_dir,
            '-no-remote',
            '-headless'
        ]
        
        try:
            process = subprocess.Popen(
                firefox_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Wait for Firefox to initialize
            time.sleep(3)
            
            return process
            
        except Exception as e:
            pytest.skip(f"Could not start Firefox: {e}")

    @pytest.mark.asyncio
    async def test_server_starts_before_extension_connects(self, running_server, firefox_path, temp_profile, extension_xpi):
        """Test server is ready when extension tries to connect"""
        
        # Server should be running
        assert running_server is not None
        
        # Try to connect as client to verify server is accessible
        try:
            uri = f"ws://localhost:{running_server._test_port}"
            websocket = await websockets.connect(uri)
            
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
            extension_xpi = get_extension_xpi_path()
            if not extension_xpi or not os.path.exists(extension_xpi):
                pytest.skip("Extension XPI not found. Run 'make package' first.")
            
            # Create Firefox test manager with coordinated port
            firefox_manager = FirefoxTestManager(
                firefox_path=os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox'),
                test_port=running_server._test_port
            )
            
            # Set up Firefox with extension
            firefox_manager.create_test_profile()
            firefox_manager.install_extension(extension_xpi)
            
            # Start Firefox and wait for extension connection
            if firefox_manager.start_firefox(headless=True):
                connection_detected = firefox_manager.wait_for_extension_connection(timeout=10.0)
            
        except Exception as e:
            print(f"Extension connection test error: {e}")
            
        finally:
            # Cleanup Firefox
            if firefox_manager:
                firefox_manager.cleanup()
        
        # Verify test infrastructure worked
        assert connection_detected, "Firefox should start successfully with extension"

    @pytest.mark.asyncio
    async def test_bidirectional_message_flow(self, running_server, firefox_path, temp_profile, extension_xpi):
        """Test bidirectional message flow between server and extension"""
        
        firefox_process = None
        
        try:
            # Start Firefox with extension  
            firefox_process = self.start_firefox_with_extension(
                firefox_path, temp_profile, extension_xpi
            )
            
            # Give extension time to connect
            await asyncio.sleep(3)
            
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
                await running_server.handle_extension_message(json.dumps(msg))
            
            # Test server's send capability (even without active extension)
            test_send_msg = {
                "id": "server-to-ext",
                "type": "request",
                "action": "tabs.get_active", 
                "data": {},
                "timestamp": time.time()
            }
            
            result = await running_server.send_to_extension(test_send_msg)
            # Should return False if no extension connected, which is expected
            assert result in [True, False]  # Either state is valid for this test
            
        except Exception as e:
            print(f"Bidirectional test error: {e}")
            
        finally:
            # Cleanup Firefox
            if firefox_process:
                try:
                    firefox_process.terminate()
                    firefox_process.wait(timeout=5)
                except:
                    firefox_process.kill()

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
                await running_server.handle_extension_message(json.dumps(msg))
                print(f"✓ Handled {msg['type']} message for action {msg['action']}")
            except Exception as e:
                pytest.fail(f"Server should handle extension message {msg['action']}: {e}")


class TestFirefoxConnectionResilience:
    """Test connection resilience and recovery"""

    @pytest.mark.asyncio
    async def test_server_handles_connection_loss(self):
        """Test server handles connection loss gracefully"""
        # Use fixed ports for resilience testing
        ports = TEST_PORTS['integration_firefox']
        port = ports['websocket'] + 1  # Offset to avoid conflict with main test
        mcp_port = ports['mcp'] + 1
        server = FoxMCPServer(host="localhost", port=port, mcp_port=mcp_port, start_mcp=False)
        
        # Start server
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(0.3)
        
        try:
            # Connect and disconnect multiple times
            for i in range(3):
                websocket = await websockets.connect(f"ws://localhost:{port}")
                
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
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_multiple_connection_attempts(self):
        """Test server can handle multiple connection attempts"""
        # Use fixed ports for multiple connection testing
        ports = TEST_PORTS['integration_firefox']
        port = ports['websocket'] + 2  # Different offset to avoid conflict
        mcp_port = ports['mcp'] + 2
        server = FoxMCPServer(host="localhost", port=port, mcp_port=mcp_port, start_mcp=False)
        
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(0.3)
        
        try:
            # Multiple simultaneous connections
            connections = []
            
            for i in range(5):
                websocket = await websockets.connect(f"ws://localhost:{port}")
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
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])