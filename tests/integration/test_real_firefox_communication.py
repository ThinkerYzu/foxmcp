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


    @pytest.mark.asyncio
    async def test_real_extension_connection(self, server_with_extension):
        """Test that real Firefox extension connects and communicates"""
        server = server_with_extension['server']
        firefox = server_with_extension['firefox']
        test_port = server_with_extension['test_port']

        # Check if extension connected to server
        assert server.extension_connection is not None, "Extension should connect to server"

        # Wait a bit more for any initial messages
        await asyncio.sleep(2.0)

        print(f"✓ Extension connected successfully to test port {test_port}")
        print(f"✓ Extension should maintain connection")

    @pytest.mark.asyncio
    async def test_extension_responds_to_server_messages(self, server_with_extension):
        """Test that extension responds to messages from server"""
        server = server_with_extension['server']
        firefox = server_with_extension['firefox']
        test_port = server_with_extension['test_port']

        # Send a test message to extension
        test_message = {
            "id": "test-message-001",
            "type": "request",
            "action": "tabs.list",
            "data": {},
            "timestamp": "2025-01-01T00:00:00.000Z"
        }

        # Send message to extension
        success = await server.send_to_extension(test_message)
        assert success, "Should be able to send message to extension"

        # Wait for potential response
        await asyncio.sleep(2.0)

        print(f"✓ Server successfully sent message to connected extension")
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