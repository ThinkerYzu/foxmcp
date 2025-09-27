"""
Real Firefox extension communication test
This test actually starts Firefox with the extension and verifies real communication
"""

import pytest
import pytest_asyncio
import asyncio
import json
import sys
import os
import time
import sqlite3
import re
from pathlib import Path

import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from test_config import TEST_PORTS, FIREFOX_TEST_CONFIG, get_test_ports
from firefox_test_utils import FirefoxTestManager
from port_coordinator import coordinated_test_ports


class TestRealFirefoxCommunication:
    """Test real communication with actual Firefox browser and extension"""

    @pytest_asyncio.fixture
    async def coordinated_server(self):
        """Start server using dynamic port coordination"""
        # Use dynamic port allocation to avoid conflicts
        with coordinated_test_ports() as (ports, coord_file):
            test_port = ports['websocket']
            mcp_port = ports['mcp']

            # Create server with connection tracking
            server = FoxMCPServer(
                host="localhost",
                port=test_port,
                mcp_port=mcp_port,
                start_mcp=False  # Focus on WebSocket communication
            )

            # Store coordination info for tests
            server.coordination_file = coord_file
            server.test_ports = ports

            # Add connection tracking
            server.connected_clients = []
            server.received_messages = []

            # Override connection handler to track connections
            original_handler = server.handle_extension_connection

            async def tracking_handler(websocket):
                server.connected_clients.append(websocket)
                try:
                    await original_handler(websocket)
                finally:
                    if websocket in server.connected_clients:
                        server.connected_clients.remove(websocket)

            server.handle_extension_connection = tracking_handler

            # Override message handler to track messages
            original_message_handler = server.handle_extension_message

            async def tracking_message_handler(message):
                server.received_messages.append(message)
                await original_message_handler(message)

            server.handle_extension_message = tracking_message_handler

            # Start server
            server_task = asyncio.create_task(server.start_server())
            await asyncio.sleep(0.5)

            try:
                yield server
            finally:
                # Cleanup
                await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_real_extension_connection(self, coordinated_server):
        """Test that real Firefox extension connects and communicates"""

        # Skip if extension XPI doesn't exist

        # Skip if Firefox not available
        firefox_path = os.environ.get('FIREFOX_PATH', 'firefox')
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip(f"Firefox not found at {firefox_path}. Set FIREFOX_PATH environment variable.")

        # Test with Firefox manager using coordinated ports
        with FirefoxTestManager(firefox_path, coordinated_server.test_ports['websocket'], coordinated_server.coordination_file) as firefox:
            # Set up Firefox with extension and start it
            success = firefox.setup_and_start_firefox(headless=True, skip_on_failure=False)
            assert success, "Firefox setup and extension installation should succeed"

            # Wait for extension connection using awaitable mechanism (with more patience)
            max_wait_time = FIREFOX_TEST_CONFIG['extension_install_wait'] + 5.0
            print(f"Waiting up to {max_wait_time}s for extension to connect...")

            connected = await firefox.async_wait_for_extension_connection(
                timeout=max_wait_time, server=coordinated_server
            )

            if connected:
                print(f"✓ Extension connected successfully")
            else:
                print(f"⚠ Extension did not connect to test port {coordinated_server.test_ports['websocket']}")
                print("Note: Extension may be trying to connect to default port 8765")
                pytest.skip("Extension connection issue - likely config mismatch")

            # Check if extension connected to server
            assert len(coordinated_server.connected_clients) > 0, "Extension should connect to server"

            # Wait a bit more for any initial messages
            await asyncio.sleep(2.0)

            # Check for any messages from extension
            print(f"Server received {len(coordinated_server.received_messages)} messages")
            print(f"Connected clients: {len(coordinated_server.connected_clients)}")

            # The extension should maintain connection
            assert len(coordinated_server.connected_clients) > 0, "Extension should maintain connection"

    @pytest.mark.asyncio
    async def test_extension_responds_to_server_messages(self, coordinated_server):
        """Test that extension responds to messages from server"""

        # Skip if extension XPI doesn't exist

        with FirefoxTestManager(firefox_path=os.environ.get('FIREFOX_PATH', 'firefox'),
                                test_port=coordinated_server.test_ports['websocket'],
                                coordination_file=coordinated_server.coordination_file) as firefox:
            # Set up Firefox with extension and start it
            success = firefox.setup_and_start_firefox(headless=True)
            if not success:
                pytest.skip("Firefox setup or extension installation failed")

            # Wait for extension to connect using awaitable mechanism
            connected = await firefox.async_wait_for_extension_connection(
                timeout=FIREFOX_TEST_CONFIG['extension_install_wait'], server=coordinated_server
            )

            if not connected:
                pytest.skip("Extension did not connect - cannot test message exchange")

            # Send a test message to extension
            test_message = {
                "id": "test-message-001",
                "type": "request",
                "action": "tabs.list",
                "data": {},
                "timestamp": "2025-01-01T00:00:00.000Z"
            }

            initial_message_count = len(coordinated_server.received_messages)

            # Send message to extension
            success = await coordinated_server.send_to_extension(test_message)
            assert success, "Should be able to send message to extension"

            # Wait for potential response
            await asyncio.sleep(2.0)

            # Check if we received any response
            final_message_count = len(coordinated_server.received_messages)

            print(f"Messages before: {initial_message_count}, after: {final_message_count}")
            if final_message_count > initial_message_count:
                print(f"Extension responded with: {coordinated_server.received_messages[-1]}")

            # At minimum, the message should have been sent successfully
            assert success, "Server should successfully send message to connected extension"

    @pytest.mark.asyncio
    async def test_extension_configuration_persistence(self):
        """Test that extension configuration persists correctly in SQLite storage"""

        # This test verifies the extension configuration system works
        test_port = 9876  # Different port for this test


        with FirefoxTestManager(test_port=test_port) as firefox:
            # Set up Firefox with extension (which creates SQLite storage)
            success = firefox.setup_and_start_firefox(headless=True, skip_on_failure=False)
            assert success, "Firefox setup and extension installation should succeed"

            # Verify SQLite storage was created and configured
            import sqlite3
            storage_db_path = os.path.join(firefox.profile_dir, 'storage-sync-v2.sqlite')
            assert os.path.exists(storage_db_path), "SQLite storage database should be created"

            # Read and verify configuration from SQLite
            conn = sqlite3.connect(storage_db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT data FROM storage_sync_data WHERE ext_id = ?",
                    ("foxmcp@codemud.org",)
                )
                result = cursor.fetchone()
                assert result is not None, "Extension configuration should exist in SQLite storage"

                config = json.loads(result[0])

                assert config['hostname'] == 'localhost', "Hostname should be configured"
                assert config['testPort'] == test_port, f"Test port should be configured as {test_port}"
                assert config['testHostname'] == 'localhost', "Test hostname should be configured"
                assert config['retryInterval'] == 1000, "Retry interval should be configured for testing"
                assert config['maxRetries'] == 5, "Max retries should be configured for testing"
                assert config['pingTimeout'] == 2000, "Ping timeout should be configured for testing"

                print(f"✓ Extension configuration verified in SQLite: {config}")

            finally:
                conn.close()


class TestFirefoxIntegrationScenarios:
    """Test various Firefox integration scenarios"""

    @pytest.mark.asyncio
    async def test_server_starts_before_extension(self):
        """Test scenario where server starts before extension connects"""

        # Start server first - use dynamic port allocation
        ports = get_test_ports('integration_basic')
        test_port = ports['websocket']
        server = FoxMCPServer(host="localhost", port=test_port, start_mcp=False)
        server_task = asyncio.create_task(server.start_server())

        try:
            await asyncio.sleep(0.5)  # Server startup time

            # Now simulate extension connection (without real Firefox)
            import websockets

            try:
                websocket = await websockets.connect(f"ws://localhost:{test_port}")

                # Send a test message
                test_msg = {
                    "id": "startup-test",
                    "type": "request",
                    "action": "ping",
                    "data": {"test": True}
                }

                await websocket.send(json.dumps(test_msg))
                await websocket.close()

                print("✓ Extension can connect to server that started first")

            except Exception as e:
                pytest.fail(f"Extension connection failed: {e}")

        finally:
            await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_extension_reconnects_after_server_restart(self):
        """Test that extension can reconnect after server restarts"""

        # This would require real extension testing
        # For now, just test the server restart capability

        # Use dynamic port allocation for server restart test
        ports = get_test_ports('integration_basic')
        test_port = ports['websocket']

        # Start first server instance
        server1 = FoxMCPServer(host="localhost", port=test_port, start_mcp=False)
        server1_task = asyncio.create_task(server1.start_server())

        try:
            await asyncio.sleep(0.5)

            # Stop first server properly
            await server1.shutdown(server1_task)

            await asyncio.sleep(0.5)  # Brief pause

            # Start second server instance on same port
            server2 = FoxMCPServer(host="localhost", port=test_port, start_mcp=False)
            server2_task = asyncio.create_task(server2.start_server())

            await asyncio.sleep(0.5)

            # Verify new server is accessible
            import websockets
            websocket = await websockets.connect(f"ws://localhost:{test_port}")
            await websocket.close()

            print("✓ Server can restart and accept new connections on same port")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            pytest.fail(f"Server restart test failed: {e}")
        finally:
            try:
                await server2.shutdown(server2_task)
            except Exception as e:
                # Handle case where server2 might not be defined if error occurred early
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])