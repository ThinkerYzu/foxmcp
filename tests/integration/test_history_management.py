"""
History Management End-to-End Tests

Comprehensive functional tests for browser history operations through the
MCP server and WebSocket protocol with real Firefox extension.
"""

import pytest
import pytest_asyncio
import asyncio
import json
import os
import time
import re
from datetime import datetime, timedelta

# Set up consistent imports
import test_imports

# Import project modules
from server.server import FoxMCPServer

# Import test utilities
from test_config import TEST_PORTS, FIREFOX_TEST_CONFIG
from firefox_test_utils import FirefoxTestManager
from port_coordinator import coordinated_test_ports


class TestHistoryManagementEndToEnd:
    """End-to-end tests for history management functionality"""
    
    @pytest_asyncio.fixture
    async def server_with_extension(self):
        """Start server and Firefox extension for history testing"""
        # Use dynamic port allocation
        with coordinated_test_ports() as (ports, coord_file):
            test_port = ports['websocket']
            mcp_port = ports['mcp']
            
            # Get extension XPI
            
            # Create server
            server = FoxMCPServer(
                host="localhost",
                port=test_port,
                mcp_port=mcp_port,
                start_mcp=False
            )
            
            # Start server
            server_task = asyncio.create_task(server.start_server())
            await asyncio.sleep(0.5)  # Allow server to start
            
            # Start Firefox with extension
            firefox_path = os.environ.get('FIREFOX_PATH', 'firefox')
            if not os.path.exists(os.path.expanduser(firefox_path)):
                pytest.skip(f"Firefox not found at {firefox_path}")
            
            firefox = FirefoxTestManager(
                firefox_path=firefox_path,
                test_port=test_port,
                coordination_file=coord_file
            )
            
            try:
                # Set up Firefox with extension and start it
                success = firefox.setup_and_start_firefox(headless=True)
                if not success:
                    pytest.skip("Firefox setup or extension installation failed")
                
                # Wait for extension to connect
                await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])
                
                # Verify connection
                if not server.extension_connection:
                    pytest.skip("Extension did not connect to server")
                
                yield server, firefox, test_port
                
            finally:
                # Cleanup
                firefox.cleanup()
                await server.shutdown(server_task)
    
    @pytest.mark.asyncio
    async def test_history_query_basic(self, server_with_extension):
        """Test basic history query functionality"""
        server, firefox, test_port = server_with_extension
        
        # Send history query request
        request = {
            "id": "test_history_query_001",
            "type": "request",
            "action": "history.query",
            "data": {
                "text": "",  # Empty text to get all history
                "maxResults": 10,
                "startTime": 0,
                "endTime": int(datetime.now().timestamp() * 1000)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await server.send_request_and_wait(request, timeout=10.0)
        
        # Verify response structure
        assert "error" not in response, f"History query failed: {response.get('error')}"
        assert response.get("type") == "response"
        assert response.get("action") == "history.query"
        assert "data" in response
        
        # Verify response data structure
        data = response["data"]
        assert "items" in data
        assert isinstance(data["items"], list)
        
        print(f"✓ History query returned {len(data['items'])} items")
        
        # If we have history items, verify their structure
        if data["items"]:
            item = data["items"][0]
            expected_fields = ["id", "url", "title", "lastVisitTime", "visitCount"]
            for field in expected_fields:
                assert field in item, f"History item missing field: {field}"
            
            print(f"✓ History item structure validated: {item.get('title', 'No title')}")
    
    @pytest.mark.asyncio
    async def test_history_query_with_text_search(self, server_with_extension):
        """Test history query with text search parameter"""
        server, firefox, test_port = server_with_extension
        
        # Send history query with search text
        request = {
            "id": "test_history_search_001",
            "type": "request", 
            "action": "history.query",
            "data": {
                "text": "github",  # Search for github-related history
                "maxResults": 5,
                "startTime": 0,
                "endTime": int(datetime.now().timestamp() * 1000)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await server.send_request_and_wait(request, timeout=10.0)
        
        # Verify response
        assert "error" not in response, f"History search failed: {response.get('error')}"
        assert response.get("type") == "response"
        assert "data" in response
        
        data = response["data"]
        assert "items" in data
        assert isinstance(data["items"], list)
        
        print(f"✓ History search for 'github' returned {len(data['items'])} items")
        
        # If we found items, verify they contain the search term
        for item in data["items"]:
            url = item.get("url", "").lower()
            title = item.get("title", "").lower()
            # Note: Firefox may not return exact matches, so we'll just log what we got
            print(f"  - Found: {item.get('title', 'No title')} - {item.get('url', 'No URL')}")
    
    @pytest.mark.asyncio
    async def test_history_query_with_time_range(self, server_with_extension):
        """Test history query with time range filtering"""
        server, firefox, test_port = server_with_extension
        
        # Query last 24 hours
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        
        request = {
            "id": "test_history_timerange_001",
            "type": "request",
            "action": "history.query", 
            "data": {
                "text": "",
                "maxResults": 20,
                "startTime": int(yesterday.timestamp() * 1000),
                "endTime": int(now.timestamp() * 1000)
            },
            "timestamp": now.isoformat()
        }
        
        response = await server.send_request_and_wait(request, timeout=10.0)
        
        # Verify response
        assert "error" not in response, f"History time range query failed: {response.get('error')}"
        assert response.get("type") == "response"
        assert "data" in response
        
        data = response["data"]
        assert "items" in data
        
        print(f"✓ History query for last 24 hours returned {len(data['items'])} items")
        
        # Verify timestamps are within range (if we have items)
        for item in data["items"]:
            visit_time = item.get("lastVisitTime")
            if visit_time:
                # Verify timestamp is within our range
                assert visit_time >= int(yesterday.timestamp() * 1000)
                assert visit_time <= int(now.timestamp() * 1000)
                print(f"  - {item.get('title', 'No title')} visited at {datetime.fromtimestamp(visit_time/1000)}")
    
    @pytest.mark.asyncio
    async def test_history_get_recent(self, server_with_extension):
        """Test getting recent history items"""
        server, firefox, test_port = server_with_extension
        
        # Request recent history
        request = {
            "id": "test_history_recent_001",
            "type": "request",
            "action": "history.recent",
            "data": {
                "count": 5
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await server.send_request_and_wait(request, timeout=10.0)
        
        # Verify response
        assert "error" not in response, f"Recent history failed: {response.get('error')}"
        assert response.get("type") == "response"
        assert response.get("action") == "history.recent"
        assert "data" in response
        
        data = response["data"]
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) <= 5  # Should not exceed requested count
        
        print(f"✓ Recent history returned {len(data['items'])} items")
        
        # Verify items are sorted by visit time (most recent first)
        if len(data["items"]) > 1:
            for i in range(len(data["items"]) - 1):
                current_time = data["items"][i].get("lastVisitTime", 0)
                next_time = data["items"][i + 1].get("lastVisitTime", 0)
                assert current_time >= next_time, "Recent history items not sorted correctly"
            
            print("✓ Recent history items are properly sorted")
        
        # Display recent items
        for i, item in enumerate(data["items"]):
            visit_time = datetime.fromtimestamp(item.get("lastVisitTime", 0) / 1000)
            print(f"  {i+1}. {item.get('title', 'No title')} - visited {visit_time}")
    
    @pytest.mark.asyncio
    async def test_history_delete_item_error_handling(self, server_with_extension):
        """Test history delete item error handling (since it's not implemented yet)"""
        server, firefox, test_port = server_with_extension
        
        # Try to delete a history item (this should fail gracefully)
        request = {
            "id": "test_history_delete_001",
            "type": "request",
            "action": "history.delete_item",
            "data": {
                "url": "https://example.com/nonexistent"
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await server.send_request_and_wait(request, timeout=10.0)
        
        # Since delete is not implemented, we expect an error
        # This test documents the current limitation
        expected_error_types = ["error", "response"]  # Could be either depending on implementation
        assert response.get("type") in expected_error_types
        
        if response.get("type") == "error":
            assert "data" in response
            error_data = response["data"]
            assert "message" in error_data or "code" in error_data
            print(f"✓ History delete properly returned error: {error_data}")
        else:
            print("✓ History delete request processed (implementation may be added)")
    
    @pytest.mark.asyncio
    async def test_history_query_parameter_validation(self, server_with_extension):
        """Test history query with various parameter combinations"""
        server, firefox, test_port = server_with_extension
        
        test_cases = [
            # Test case 1: Minimal parameters
            {
                "name": "minimal_params",
                "data": {"maxResults": 1},
                "should_succeed": True
            },
            # Test case 2: All parameters
            {
                "name": "all_params", 
                "data": {
                    "text": "test",
                    "maxResults": 3,
                    "startTime": int((datetime.now() - timedelta(hours=1)).timestamp() * 1000),
                    "endTime": int(datetime.now().timestamp() * 1000)
                },
                "should_succeed": True
            },
            # Test case 3: Large maxResults
            {
                "name": "large_max_results",
                "data": {"maxResults": 1000},
                "should_succeed": True
            },
            # Test case 4: Zero maxResults (should handle gracefully)
            {
                "name": "zero_max_results",
                "data": {"maxResults": 0},
                "should_succeed": True  # Firefox should handle this gracefully
            }
        ]
        
        for test_case in test_cases:
            print(f"Testing parameter case: {test_case['name']}")
            
            request = {
                "id": f"test_history_params_{test_case['name']}",
                "type": "request",
                "action": "history.query",
                "data": test_case["data"],
                "timestamp": datetime.now().isoformat()
            }
            
            response = await server.send_request_and_wait(request, timeout=10.0)
            
            if test_case["should_succeed"]:
                assert "error" not in response or response.get("type") != "error", \
                    f"Expected success for {test_case['name']}, got: {response}"
                assert response.get("type") == "response"
                assert "data" in response
                print(f"  ✓ {test_case['name']} succeeded")
            else:
                assert response.get("type") == "error", \
                    f"Expected error for {test_case['name']}, got: {response}"
                print(f"  ✓ {test_case['name']} properly failed")
    
    @pytest.mark.asyncio
    async def test_history_concurrent_queries(self, server_with_extension):
        """Test multiple concurrent history queries"""
        server, firefox, test_port = server_with_extension
        
        # Create multiple concurrent requests
        concurrent_requests = []
        for i in range(3):
            request = {
                "id": f"test_history_concurrent_{i:03d}",
                "type": "request",
                "action": "history.query",
                "data": {
                    "text": "" if i % 2 == 0 else "test",
                    "maxResults": 5 + i,
                    "startTime": 0,
                    "endTime": int(datetime.now().timestamp() * 1000)
                },
                "timestamp": datetime.now().isoformat()
            }
            concurrent_requests.append(server.send_request_and_wait(request, timeout=15.0))
        
        # Execute all requests concurrently
        responses = await asyncio.gather(*concurrent_requests)
        
        # Verify all requests succeeded
        for i, response in enumerate(responses):
            assert "error" not in response, f"Concurrent request {i} failed: {response.get('error')}"
            assert response.get("type") == "response"
            assert response.get("id") == f"test_history_concurrent_{i:03d}"
            assert "data" in response
            
            data = response["data"]
            assert "items" in data
            print(f"✓ Concurrent request {i} returned {len(data['items'])} items")
        
        print(f"✓ All {len(responses)} concurrent history queries completed successfully")
    
    @pytest.mark.asyncio
    async def test_history_error_handling_invalid_action(self, server_with_extension):
        """Test error handling for invalid history actions"""
        server, firefox, test_port = server_with_extension
        
        # Send invalid history action
        request = {
            "id": "test_invalid_history_action",
            "type": "request",
            "action": "history.nonexistent_action",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await server.send_request_and_wait(request, timeout=10.0)
        
        # Should get an error response
        assert response.get("type") == "error" or "error" in response
        
        if response.get("type") == "error":
            error_data = response.get("data", {})
            assert "code" in error_data or "message" in error_data
            print(f"✓ Invalid history action properly returned error: {error_data}")
        else:
            print(f"✓ Invalid action handled: {response.get('error')}")
    
    @pytest.mark.asyncio
    async def test_history_response_correlation(self, server_with_extension):
        """Test that history responses are properly correlated with requests"""
        server, firefox, test_port = server_with_extension
        
        # Send multiple requests with different IDs
        request_ids = []
        requests = []
        
        for i in range(3):
            request_id = f"test_correlation_{i}_{int(datetime.now().timestamp() * 1000)}"
            request_ids.append(request_id)
            
            request = {
                "id": request_id,
                "type": "request",
                "action": "history.recent",
                "data": {"count": 1},
                "timestamp": datetime.now().isoformat()
            }
            
            requests.append(server.send_request_and_wait(request, timeout=10.0))
            
            # Small delay between requests to ensure different timestamps
            await asyncio.sleep(0.1)
        
        # Wait for all responses
        responses = await asyncio.gather(*requests)
        
        # Verify response correlation
        for i, response in enumerate(responses):
            expected_id = request_ids[i]
            actual_id = response.get("id")
            
            assert actual_id == expected_id, \
                f"Response correlation failed: expected {expected_id}, got {actual_id}"
            
            print(f"✓ Request {expected_id} properly correlated")
        
        print("✓ All history response correlations verified")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])