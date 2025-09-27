#!/usr/bin/env python3
"""
Test the awaitable connection mechanism for WebSocket server
This test verifies that the server can await extension connections properly
"""

import pytest
import pytest_asyncio
import asyncio
import websockets
import json
import time
import sys
import os

import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from port_coordinator import get_port_by_type

class TestAwaitableConnection:
    """Test the new awaitable connection mechanism"""

    @pytest.mark.asyncio
    async def test_wait_for_extension_connection_timeout(self):
        """Test that wait_for_extension_connection times out when no connection comes"""
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
            # Test timeout - should return False after 1 second
            start_time = time.time()
            connected = await server.wait_for_extension_connection(timeout=1.0)
            end_time = time.time()

            # Should have returned False after timeout
            assert connected is False
            assert 0.9 <= (end_time - start_time) <= 1.5  # Allow some tolerance

        finally:
            await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_wait_for_extension_connection_success(self):
        """Test that wait_for_extension_connection succeeds when connection is made"""
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
            # Start waiting for connection in a task
            wait_task = asyncio.create_task(
                server.wait_for_extension_connection(timeout=5.0)
            )

            # Give the wait_task a moment to start
            await asyncio.sleep(0.1)

            # Connect from a mock extension after a short delay
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
    async def test_multiple_waiters(self):
        """Test that multiple waiters all get notified when connection is made"""
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
            # Start multiple waiters
            wait_tasks = [
                asyncio.create_task(server.wait_for_extension_connection(timeout=5.0))
                for _ in range(3)
            ]

            # Give the wait_tasks a moment to start
            await asyncio.sleep(0.1)

            # Connect after a delay
            await asyncio.sleep(0.5)
            websocket = await websockets.connect(f"ws://localhost:{port}")

            # All waiters should complete successfully
            results = await asyncio.gather(*wait_tasks)

            assert all(result is True for result in results)
            assert server.extension_connection is not None

            # Clean up the connection
            await websocket.close()

        finally:
            await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_already_connected_returns_immediately(self):
        """Test that wait_for_extension_connection returns immediately if already connected"""
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
            # Connect first
            websocket = await websockets.connect(f"ws://localhost:{port}")

            # Give server time to register the connection
            await asyncio.sleep(0.1)

            # Now wait_for_extension_connection should return immediately
            start_time = time.time()
            connected = await server.wait_for_extension_connection(timeout=5.0)
            end_time = time.time()

            assert connected is True
            assert (end_time - start_time) < 0.1  # Should be very fast

            # Clean up the connection
            await websocket.close()

        finally:
            await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_mock_extension_message(self):
        """Test complete flow with mock extension sending a message"""
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
            # Start waiting for connection
            wait_task = asyncio.create_task(
                server.wait_for_extension_connection(timeout=5.0)
            )

            # Connect and send a message like a real extension would
            await asyncio.sleep(0.1)
            websocket = await websockets.connect(f"ws://localhost:{port}")

            # Wait should complete
            connected = await wait_task
            assert connected is True

            # Send a test message
            test_message = {
                "id": "test-message-001",
                "type": "request",
                "action": "ping",
                "data": {"test": True},
                "timestamp": time.time()
            }

            await websocket.send(json.dumps(test_message))

            # Give server time to process the message
            await asyncio.sleep(0.1)

            # Clean up the connection
            await websocket.close()

        finally:
            await server.shutdown(server_task)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])