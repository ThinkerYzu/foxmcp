#!/usr/bin/env python3
"""
Test the history polling mechanism
"""

import pytest
import pytest_asyncio
import asyncio
import sys
import os

import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from port_coordinator import get_port_by_type
from integration.test_history_with_content import wait_for_history_update

class TestHistoryPolling:
    """Test the history polling mechanism"""

    @pytest.mark.asyncio
    async def test_wait_for_history_update_timeout(self):
        """Test that wait_for_history_update times out when no results are found"""
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
            # Test timeout with a search that won't find anything
            search_criteria = {
                "text": "nonexistent_search_term_12345",
                "maxResults": 10,
                "startTime": 0,
                "endTime": 999999999999
            }

            # Use very short attempts for testing
            found, response_data = await wait_for_history_update(
                server, search_criteria, max_attempts=3, interval=0.5
            )

            # Should timeout and return False
            assert found is False
            assert response_data == {}

        finally:
            await server.shutdown(server_task)

    @pytest.mark.asyncio
    async def test_wait_for_history_update_with_mock_response(self):
        """Test wait_for_history_update with a mocked successful response"""
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
            # Mock the server's send_request_and_wait method to return a successful response
            original_method = server.send_request_and_wait

            async def mock_send_request_and_wait(request, timeout=5.0):
                # Return a successful response with results
                return {
                    "data": {
                        "results": [
                            {"url": "https://example.org/test1", "title": "Test 1"},
                            {"url": "https://example.org/test2", "title": "Test 2"}
                        ]
                    }
                }

            # Replace the method
            server.send_request_and_wait = mock_send_request_and_wait

            search_criteria = {
                "text": "example.org",
                "maxResults": 10,
                "startTime": 0,
                "endTime": 999999999999
            }

            found, response_data = await wait_for_history_update(
                server, search_criteria, max_attempts=3, interval=0.1
            )

            # Should find results immediately
            assert found is True
            assert "results" in response_data
            assert len(response_data["results"]) == 2

            # Restore original method
            server.send_request_and_wait = original_method

        finally:
            await server.shutdown(server_task)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])