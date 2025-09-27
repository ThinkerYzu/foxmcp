#!/usr/bin/env python3
"""
Test integration of Firefox test utilities with awaitable connection mechanism
"""

import test_imports  # Automatic path setup
import pytest
import pytest_asyncio
import asyncio
import websockets
import sys
import os

from server.server import FoxMCPServer
from firefox_test_utils import FirefoxTestManager
from port_coordinator import get_port_by_type

class TestFirefoxAwaitableIntegration:
    """Test Firefox test utilities with awaitable connection mechanism"""

    @pytest.mark.asyncio
    async def test_firefox_manager_async_wait_method_with_server(self):
        """Test that FirefoxTestManager.async_wait_for_extension_connection works with server"""
        port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')

        server = FoxMCPServer(
            host="localhost",
            port=port,
            mcp_port=mcp_port,
            start_mcp=False
        )

        server_task = asyncio.create_task(server.start_server())

        # Wait for server to start
        await asyncio.sleep(0.1)

        try:
            # Create Firefox manager (but don't start Firefox since we don't want to depend on it)
            firefox_manager = FirefoxTestManager(
                firefox_path="/fake/path/firefox",  # Non-existent path
                test_port=port
            )

            # Start waiting for connection in a task
            wait_task = asyncio.create_task(
                firefox_manager.async_wait_for_extension_connection(
                    timeout=2.0, server=server
                )
            )

            # Give the wait_task a moment to start
            await asyncio.sleep(0.1)

            # Simulate extension connection
            await asyncio.sleep(0.5)
            websocket = await websockets.connect(f"ws://localhost:{port}")

            # The wait should complete successfully
            connected = await wait_task

            assert connected is True
            assert server.extension_connection is not None

            # Clean up the connection
            await websocket.close()

        finally:
            await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_firefox_manager_async_wait_fallback(self):
        """Test that FirefoxTestManager.async_wait_for_extension_connection falls back when no server"""
        # Create Firefox manager without server
        firefox_manager = FirefoxTestManager(
            firefox_path="/fake/path/firefox",  # Non-existent path
            test_port=9999
        )

        # Test with no server - should fall back to time-based waiting
        start_time = asyncio.get_event_loop().time()
        connected = await firefox_manager.async_wait_for_extension_connection(
            timeout=1.0, server=None
        )
        end_time = asyncio.get_event_loop().time()

        # Should have used fallback timing mechanism (uses config value, not our timeout)
        assert connected is False  # Since Firefox isn't really running
        # The fallback uses FIREFOX_TEST_CONFIG['extension_install_wait'] which is ~3 seconds
        assert (end_time - start_time) >= 2.5  # Should have waited at least the config time

    @pytest.mark.asyncio
    async def test_firefox_manager_sync_wait_with_server(self):
        """Test that FirefoxTestManager.wait_for_extension_connection works with server (sync version)"""
        port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')

        server = FoxMCPServer(
            host="localhost",
            port=port,
            mcp_port=mcp_port,
            start_mcp=False
        )

        server_task = asyncio.create_task(server.start_server())

        # Wait for server to start
        await asyncio.sleep(0.1)

        try:
            # Create Firefox manager
            firefox_manager = FirefoxTestManager(
                firefox_path="/fake/path/firefox",  # Non-existent path
                test_port=port
            )

            # Start waiting for connection in a task (run sync method in executor)
            async def run_sync_wait():
                import asyncio
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: firefox_manager.wait_for_extension_connection(
                        timeout=2.0, server=server
                    )
                )

            wait_task = asyncio.create_task(run_sync_wait())

            # Give the wait_task a moment to start
            await asyncio.sleep(0.1)

            # Simulate extension connection
            await asyncio.sleep(0.5)
            websocket = await websockets.connect(f"ws://localhost:{port}")

            # The wait should complete successfully
            connected = await wait_task

            assert connected is True
            assert server.extension_connection is not None

            # Clean up the connection
            await websocket.close()

        finally:
            await server.shutdown(server_task)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])