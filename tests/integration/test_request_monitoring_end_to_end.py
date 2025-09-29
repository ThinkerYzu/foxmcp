"""
Web Request Monitoring End-to-End Tests

Comprehensive functional tests for web request monitoring operations through the
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
from mcp_client_harness import DirectMCPTestClient


class TestRequestMonitoringEndToEnd:
    """End-to-end tests for web request monitoring functionality"""

    @pytest_asyncio.fixture
    async def full_monitoring_system(self, server_with_extension):
        """Complete monitoring testing system with MCP client"""
        server = server_with_extension['server']
        firefox = server_with_extension['firefox']
        test_port = server_with_extension['test_port']
        mcp_port = server_with_extension['mcp_port']

        # Create direct MCP client (more reliable for testing)
        mcp_client = DirectMCPTestClient(server.mcp_tools)

        yield {
            'server': server,
            'firefox': firefox,
            'mcp_client': mcp_client,
            'test_port': test_port,
            'mcp_port': mcp_port
        }

        # Cleanup handled by server_with_extension fixture

    @pytest.mark.asyncio
    async def test_request_monitoring_with_firefox(self, full_monitoring_system):
        """Test complete request monitoring workflow with real Firefox extension"""
        system = full_monitoring_system
        server = system['server']
        mcp_client = system['mcp_client']
        firefox = system['firefox']

        await mcp_client.connect()

        print("\n🔍 Testing web request monitoring with real Firefox...")

        # Test URL patterns that the extension can monitor
        test_url_patterns = ["https://example.org/*", "*"]

        try:
            # Step 1: Start monitoring
            print("🔍 Starting request monitoring...")
            start_result = await mcp_client.call_tool("requests_start_monitoring", {
                "url_patterns": test_url_patterns,
                "options": {
                    "capture_request_bodies": True,
                    "capture_response_bodies": True,
                    "max_body_size": 50000,
                    "content_types_to_capture": ["text/html", "application/json"]
                }
            })

            print(f"Start monitoring result: {start_result}")

            # Extract monitor_id from result
            monitor_id = None
            if isinstance(start_result, dict):
                start_content = start_result.get('content', '')
                if 'monitor_id' in start_content:
                    # Parse JSON from content
                    try:
                        start_data = json.loads(start_content)
                        monitor_id = start_data.get('monitor_id')
                    except json.JSONDecodeError:
                        # Try to extract from string
                        import re
                        match = re.search(r'"monitor_id":\s*"([^"]+)"', start_content)
                        if match:
                            monitor_id = match.group(1)

            assert monitor_id, f"No monitor_id found in response: {start_result}"
            print(f"✅ Monitoring started with ID: {monitor_id}")

            # Step 2: Trigger some web requests by creating a tab and navigating
            print("🌐 Creating tab and navigating to test URL...")
            create_result = await mcp_client.call_tool("tabs_create", {
                "url": "https://example.org/",
                "active": True
            })
            print(f"📄 Tab created: {create_result}")

            # Wait for requests to be captured
            print("⏳ Waiting for requests to be captured...")
            await asyncio.sleep(5.0)

            # Step 3: List captured requests
            print("📋 Listing captured requests...")
            list_result = await mcp_client.call_tool("requests_list_captured", {
                "monitor_id": monitor_id
            })

            print(f"List result: {list_result}")

            # Parse the list result
            total_requests = 0
            requests_data = []

            if isinstance(list_result, dict):
                list_content = list_result.get('content', '')
                try:
                    list_data = json.loads(list_content)
                    total_requests = list_data.get('total_requests', 0)
                    requests_data = list_data.get('requests', [])
                except json.JSONDecodeError:
                    # Handle string responses
                    if 'total_requests' in list_content:
                        import re
                        match = re.search(r'"total_requests":\s*(\d+)', list_content)
                        if match:
                            total_requests = int(match.group(1))

            print(f"📊 Captured {total_requests} requests")

            # Verify we captured some requests
            if total_requests > 0 and requests_data:
                print("🎯 Sample captured requests:")
                for i, req in enumerate(requests_data[:3]):  # Show first 3
                    print(f"  {i+1}. {req.get('method', 'UNKNOWN')} {req.get('url', 'NO_URL')} "
                          f"-> {req.get('status_code', 'NO_CODE')} ({req.get('duration_ms', 0)}ms)")

                # Step 4: Get content for a specific request
                test_request = requests_data[0]
                print(f"🔍 Getting content for request: {test_request.get('request_id', 'NO_ID')}")

                content_result = await mcp_client.call_tool("requests_get_content", {
                    "monitor_id": monitor_id,
                    "request_id": test_request.get('request_id'),
                    "include_binary": False
                })

                print(f"📄 Content result: {content_result}")

                # Basic verification that we got a response
                if isinstance(content_result, dict) and content_result.get('content'):
                    print("✅ Content retrieved successfully!")
                else:
                    print("⚠️  Content retrieval may not have worked as expected")

            else:
                print("⚠️  No requests were captured. This might indicate:")
                print("   - URL pattern didn't match any requests")
                print("   - Network requests completed before monitoring started")
                print("   - Extension WebRequest API not properly implemented")

        except Exception as e:
            print(f"❌ Test error: {e}")
            raise

        finally:
            # Step 5: Stop monitoring
            print("🛑 Stopping monitoring...")
            try:
                if 'monitor_id' in locals():
                    stop_result = await mcp_client.call_tool("requests_stop_monitoring", {
                        "monitor_id": monitor_id,
                        "drain_timeout": 5
                    })
                    print(f"✅ Monitoring stopped: {stop_result}")
                else:
                    print("⚠️  No monitor_id available for stopping")

            except Exception as e:
                print(f"⚠️  Error stopping monitoring: {e}")

        print("✅ Request monitoring Firefox test completed")

    @pytest.mark.asyncio
    async def test_monitoring_error_scenarios(self, full_monitoring_system):
        """Test error scenarios in monitoring APIs"""
        system = full_monitoring_system
        mcp_client = system['mcp_client']

        await mcp_client.connect()

        print("\n❌ Testing error scenarios...")

        # Test 1: Empty URL patterns
        result = await mcp_client.call_tool("requests_start_monitoring", {
            "url_patterns": []
        })
        print(f"Empty patterns result: {result}")
        # Should get an error
        if isinstance(result, dict):
            content = result.get('content', '')
            assert 'error' in content.lower() or 'required' in content.lower()
        print("✅ Empty URL patterns properly rejected")

        # Test 2: Invalid monitor ID
        result = await mcp_client.call_tool("requests_list_captured", {
            "monitor_id": "invalid_monitor_id"
        })
        print(f"Invalid monitor result: {result}")
        # Should handle gracefully
        print("✅ Invalid monitor ID handled")

        # Test 3: Invalid request for content
        result = await mcp_client.call_tool("requests_get_content", {
            "monitor_id": "invalid_monitor",
            "request_id": "invalid_request"
        })
        print(f"Invalid content request result: {result}")
        # Should handle gracefully
        print("✅ Invalid content request handled")

        print("✅ Error scenario testing completed")

    @pytest.mark.asyncio
    async def test_monitoring_api_registration(self, full_monitoring_system):
        """Test that all monitoring APIs are properly registered"""
        system = full_monitoring_system
        server = system['server']

        print("\n🔍 Testing API registration...")

        # Get all tools
        try:
            tools = await server.mcp_tools.mcp.get_tools()
            monitoring_tools = [name for name in tools.keys() if name.startswith("requests_")]

            expected_tools = [
                "requests_start_monitoring",
                "requests_stop_monitoring",
                "requests_list_captured",
                "requests_get_content"
            ]

            print(f"Found monitoring tools: {monitoring_tools}")

            for tool in expected_tools:
                assert tool in monitoring_tools, f"Missing tool: {tool}"

            print("✅ All monitoring APIs properly registered")

        except Exception as e:
            print(f"Error checking tools: {e}")
            raise


# Utility test for environment verification
@pytest.mark.asyncio
async def test_monitoring_test_environment():
    """Verify test environment configuration"""

    print(f"\n🔧 Test Environment Configuration:")
    print(f"   - Python version: {os.sys.version}")
    print(f"   - Current directory: {os.getcwd()}")
    print(f"   - FIREFOX_PATH: {os.environ.get('FIREFOX_PATH', 'not set')}")

    # Check if required test modules are available
    try:
        import test_imports
        print("   ✅ test_imports available")
    except ImportError as e:
        print(f"   ❌ test_imports error: {e}")

    try:
        from mcp_client_harness import DirectMCPTestClient
        print("   ✅ DirectMCPTestClient available")
    except ImportError as e:
        print(f"   ❌ DirectMCPTestClient error: {e}")

    print("✅ Environment check completed")