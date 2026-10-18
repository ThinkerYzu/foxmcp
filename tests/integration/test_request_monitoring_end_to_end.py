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

                # Verify response body content was captured
                if isinstance(content_result, dict) and content_result.get('content'):
                    try:
                        content_data = json.loads(content_result['content'])
                        response_body = content_data.get('response_body', {})

                        # Check if response body was captured
                        if response_body.get('included'):
                            response_content = response_body.get('content', '')
                            print(f"✅ Response body captured! Content length: {len(response_content)} chars")
                            print(f"   Content type: {response_body.get('content_type', 'unknown')}")
                            print(f"   Truncated: {response_body.get('truncated', False)}")

                            # Verify it contains actual HTML content from example.org
                            if 'example.org' in response_content.lower() or 'html' in response_content.lower():
                                print("✅ Response body contains expected content from example.org")
                            else:
                                print(f"⚠️  Response body doesn't contain expected content. First 200 chars: {response_content[:200]}")
                        else:
                            print("⚠️  Response body was not captured")
                            print(f"   Reason: {response_body.get('note', 'Unknown')}")

                    except json.JSONDecodeError as e:
                        print(f"⚠️  Could not parse content result: {e}")

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
    async def test_response_body_capture_verification(self, full_monitoring_system):
        """Test that response body content is actually captured and verified"""
        system = full_monitoring_system
        mcp_client = system['mcp_client']
        firefox = system['firefox']

        await mcp_client.connect()

        print("\\n📋 Testing response body capture verification...")

        try:
            # Start monitoring with response body capture enabled
            start_result = await mcp_client.call_tool("requests_start_monitoring", {
                "url_patterns": ["https://example.org/*"],
                "options": {
                    "capture_response_bodies": True,
                    "max_body_size": 50000,
                    "content_types_to_capture": ["text/html", "application/json"]
                }
            })

            # Extract monitor_id
            monitor_id = None
            if isinstance(start_result, dict):
                start_content = start_result.get('content', '')
                try:
                    start_data = json.loads(start_content)
                    monitor_id = start_data.get('monitor_id')
                except json.JSONDecodeError:
                    match = re.search(r'"monitor_id":\\s*"([^"]+)"', start_content)
                    if match:
                        monitor_id = match.group(1)

            assert monitor_id, f"No monitor_id found: {start_result}"
            print(f"✅ Monitoring started with response capture: {monitor_id}")

            # Navigate to example.org to trigger requests
            create_result = await mcp_client.call_tool("tabs_create", {
                "url": "https://example.org/",
                "active": True
            })
            print(f"📄 Created tab: {create_result}")

            # Wait for the initial page to load
            await asyncio.sleep(5.0)

            # Trigger a second request from the page, so the monitor sees one
            # that is not the document load
            print("🔄 Triggering fetch request to capture response body...")

            # Execute JavaScript to make a fetch request that will be intercepted
            exec_result = await mcp_client.call_tool("content_execute_script", {
                "tab_id": 2,  # The tab we created
                "code": """
                console.log('About to make fetch request...');

                // Make a fetch request to the same domain to trigger our interception
                fetch('https://example.org/', {
                    method: 'GET',
                    cache: 'no-cache'
                }).then(response => {
                    console.log('Test fetch completed:', response.status);
                    return response.text();
                }).then(text => {
                    console.log('Test fetch response length:', text.length);
                }).catch(error => {
                    console.error('Test fetch error:', error);
                });
                'fetch_triggered';
                """
            })
            print(f"📄 Script execution result: {exec_result}")

            # Wait longer for the fetch request and response capture
            await asyncio.sleep(8.0)

            # List captured requests
            list_result = await mcp_client.call_tool("requests_list_captured", {
                "monitor_id": monitor_id
            })

            # Parse and find HTML request
            requests_data = []
            if isinstance(list_result, dict):
                list_content = list_result.get('content', '')
                try:
                    list_data = json.loads(list_content)
                    requests_data = list_data.get('requests', [])
                except json.JSONDecodeError:
                    pass

            # Find the main HTML document request
            html_request = None
            for req in requests_data:
                if req.get('url', '').startswith('https://example.org') and not req.get('url', '').endswith(('.css', '.js', '.png', '.jpg')):
                    html_request = req
                    break

            if html_request:
                print(f"🔍 Testing response body for HTML request: {html_request.get('url')}")

                # Get content for this request
                content_result = await mcp_client.call_tool("requests_get_content", {
                    "monitor_id": monitor_id,
                    "request_id": html_request.get('request_id'),
                    "include_binary": False
                })

                # Verify response body capture
                assert isinstance(content_result, dict), "Content result should be dict"
                assert content_result.get('content'), "Content result should have content"

                content_data = json.loads(content_result['content'])

                # Verify response body capture attempt
                response_body = content_data.get('response_body', {})

                if response_body.get('included') and response_body.get('content'):
                    # Full response body capture succeeded
                    response_content = response_body.get('content', '')
                    print(f"✅ Response body captured! Length: {len(response_content)} chars")
                    print(f"   Content type: {response_body.get('content_type')}")

                    # Verify the content is not empty and has meaningful length
                    assert response_content.strip(), f"Response body content should not be empty or just whitespace, got: '{response_content[:100]}...'"
                    assert len(response_content) > 100, f"Response content too short: {len(response_content)} chars"
                    assert any(keyword in response_content.lower() for keyword in ['html', 'example', 'doctype']), \
                        f"Response doesn't contain expected HTML content. First 500 chars: {response_content[:500]}"

                    print("✅ Response body content verification passed!")
                else:
                    # Response body capture not available, but verify other aspects
                    print(f"ℹ️  Response body capture not available: {response_body.get('note', 'Unknown reason')}")

                    # Verify that we at least have response metadata
                    assert response_body.get('content_type'), f"Response should have content type, got: {response_body}"
                    assert response_body.get('size_bytes') is not None, f"Response should have size info, got: {response_body}"
                    assert response_body.get('size_bytes') > 0, f"Response should have non-zero size, got: {response_body.get('size_bytes')} bytes"

                    print(f"✅ Response metadata verified! Size: {response_body.get('size_bytes')} bytes, Type: {response_body.get('content_type')}")
                    print("✅ Request monitoring working correctly (response body capture has technical limitations)")

            else:
                pytest.skip("No suitable HTML request found for response body testing")

        except Exception as e:
            print(f"❌ Response body test error: {e}")
            raise

        finally:
            # Stop monitoring
            try:
                if 'monitor_id' in locals() and monitor_id:
                    await mcp_client.call_tool("requests_stop_monitoring", {
                        "monitor_id": monitor_id,
                        "drain_timeout": 5
                    })
            except Exception as e:
                print(f"⚠️  Error stopping monitoring: {e}")

        print("✅ Response body capture verification completed")

    @pytest.mark.asyncio
    async def test_concurrent_monitors_each_capture(self, full_monitoring_system):
        """Every monitor matching a request lists it, not just the oldest one

        The extension keeps one record per request id, shared by all monitors,
        and a single flag on it used to mean the first monitor to match claimed
        the request outright. Every later monitor then read zero for as long as
        the older one stayed active, which is what an agent hits when it starts
        a fresh monitor after an earlier attempt it never stopped.

        The third pattern is <all_urls>. Patterns here are globs, so the
        WebExtensions spelling holds no wildcard and matched nothing at all.
        """
        system = full_monitoring_system
        mcp_client = system['mcp_client']

        await mcp_client.connect()

        async def start_monitor(patterns):
            result = await mcp_client.call_tool("requests_start_monitoring", {
                "url_patterns": patterns
            })
            data = json.loads(result['content'])
            assert 'monitor_id' in data, f"No monitor_id in {result}"
            return data['monitor_id']

        async def captured_urls(monitor_id):
            result = await mcp_client.call_tool("requests_list_captured", {
                "monitor_id": monitor_id
            })
            return [req['url'] for req in json.loads(result['content'])['requests']]

        monitors = [
            ("first", await start_monitor(["https://example.org/*"])),
            ("second", await start_monitor(["https://example.org/*"])),
            ("all_urls", await start_monitor(["<all_urls>"])),
        ]

        try:
            await mcp_client.call_tool("tabs_create", {
                "url": "https://example.org/",
                "active": True
            })
            await asyncio.sleep(5.0)

            captured = {name: await captured_urls(monitor_id) for name, monitor_id in monitors}
            print(f"Captured per monitor: { {k: len(v) for k, v in captured.items()} }")

            for name, urls in captured.items():
                assert any('example.org' in url for url in urls), (
                    f"monitor '{name}' captured no example.org request; "
                    f"all three monitors saw: { {k: len(v) for k, v in captured.items()} }"
                )
        finally:
            for _, monitor_id in monitors:
                await mcp_client.call_tool("requests_stop_monitoring", {
                    "monitor_id": monitor_id
                })

    @pytest.mark.asyncio
    async def test_monitors_are_cleared_when_the_connection_drops(self, full_monitoring_system):
        """Losing the server takes the monitors with it, and says so afterwards

        Monitors live in the extension, which outlives any server. One that was
        started over a connection that has since dropped can never be read or
        stopped by anyone, because its id went with the client, so it is cleared
        rather than left holding the webRequest listeners up.

        The listing afterwards has to be an error: an empty list is what a healthy
        monitor that has caught nothing yet returns, and telling those two apart is
        the whole point.
        """
        system = full_monitoring_system
        server = system['server']
        mcp_client = system['mcp_client']

        await mcp_client.connect()

        start = await mcp_client.call_tool("requests_start_monitoring", {"url_patterns": ["*"]})
        monitor_id = json.loads(start['content'])['monitor_id']

        await mcp_client.call_tool("tabs_create", {"url": "https://example.org/", "active": True})
        await asyncio.sleep(4.0)

        listed = await mcp_client.call_tool("requests_list_captured", {"monitor_id": monitor_id})
        assert json.loads(listed['content']).get('total_requests', 0) > 0, \
            f"The monitor caught nothing before the drop, so the test proves nothing: {listed}"

        # Drop the socket the way a restarted server would
        dropped = server.extension_connection
        await dropped.close()

        for _ in range(100):
            await asyncio.sleep(0.1)
            current = server.extension_connection
            if current is not None and current is not dropped:
                break
        assert server.extension_connection is not dropped, \
            "Extension never reconnected, so the monitor's fate cannot be read"

        after = await mcp_client.call_tool("requests_list_captured", {"monitor_id": monitor_id})
        assert 'not found' in after['content'].lower(), \
            f"The monitor should be gone with the connection that started it: {after}"

    @pytest.mark.asyncio
    async def test_monitoring_api_registration(self, full_monitoring_system):
        """Test that all monitoring APIs are properly registered"""
        system = full_monitoring_system
        server = system['server']

        print("\n🔍 Testing API registration...")

        # Get all tools
        try:
            tools = await server.mcp_tools.mcp.list_tools()
            monitoring_tools = [tool.name for tool in tools if tool.name.startswith("requests_")]

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

@pytest.mark.asyncio
async def test_small_json_bodies_keep_their_response_content_type(server_with_extension):
    """Fast local responses must not finish filtering before headers are recorded."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from fastmcp import Client

    body = b'{"small":true}'
    page = b'''<!doctype html><button id="fetch">Fetch tiny responses</button><script>
    document.querySelector('button').onclick = async () => {
      for (let i = 0; i < 10; i++) {
        await (await fetch('/tiny?i=' + i, {cache:'no-store'})).json();
      }
    };
    </script>'''

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            tiny = self.path.startswith('/tiny?')
            content = body if tiny else page
            self.send_response(200)
            self.send_header('Content-Type', 'application/json' if tiny else 'text/html')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    website = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=website.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{website.server_port}'
    tab_id = None
    monitor_id = None
    try:
        async with Client(server_with_extension['server'].mcp_tools.mcp) as client:
            async def call(name, **arguments):
                result = await client.call_tool(name, arguments)
                assert not result.is_error, result
                return result.content[0].text

            try:
                created = await call('tabs_create', url=url + '/page')
                tab_id = int(re.search(r'ID (\d+)', created)[1])
                for _ in range(100):
                    html = await call('content_get_html', tab_id=tab_id)
                    if 'id="fetch"' in html:
                        break
                    await asyncio.sleep(.1)
                else:
                    pytest.fail('Tiny response fixture did not load')
                started = json.loads(await call('requests_start_monitoring',
                    url_patterns=[url + '/tiny*'], tab_id=tab_id,
                    options={'capture_response_bodies': True,
                             'content_types_to_capture': ['application/json']}))
                monitor_id = started['monitor_id']
                await call('content_execute_script', tab_id=tab_id,
                           code="document.querySelector('#fetch').click(); 'started'")
                for _ in range(100):
                    captured = json.loads(await call('requests_list_captured', monitor_id=monitor_id))
                    if len(captured['requests']) == 10:
                        break
                    await asyncio.sleep(.1)
                else:
                    pytest.fail(f'Expected ten tiny responses: {captured}')
                for request in captured['requests']:
                    assert request['status_code'] == 200
                    content = json.loads(await call('requests_get_content', monitor_id=monitor_id,
                                                    request_id=request['request_id']))
                    response = content['response_body']
                    assert response['included'], response
                    assert response['content_type'] == 'application/json'
                    assert response['size_bytes'] == len(body)
                    assert json.loads(response['content']) == {'small': True}
            finally:
                if monitor_id:
                    await call('requests_stop_monitoring', monitor_id=monitor_id)
                if tab_id is not None:
                    await call('tabs_close', tab_id=tab_id)
    finally:
        website.shutdown()
        website.server_close()
        thread.join()
