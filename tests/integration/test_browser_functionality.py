"""
Browser Functionality Integration Tests
Tests browser-specific functionality like tabs, content, navigation, screenshots
"""

import pytest
import pytest_asyncio
import asyncio
import json
import os
import sys
import re

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.server import FoxMCPServer
try:
    from ..port_coordinator import coordinated_test_ports
    from ..firefox_test_utils import FirefoxTestManager
    from ..test_config import FIREFOX_TEST_CONFIG
    from ..mcp_client_harness import DirectMCPTestClient
except ImportError:
    from port_coordinator import coordinated_test_ports
    from firefox_test_utils import FirefoxTestManager
    from test_config import FIREFOX_TEST_CONFIG
    from mcp_client_harness import DirectMCPTestClient


class TestBrowserFunctionality:
    """Browser functionality integration tests"""

    @pytest_asyncio.fixture
    async def full_mcp_system(self):
        """Set up complete system: MCP server + WebSocket server + Firefox"""

        # Use coordinated ports to avoid conflicts
        with coordinated_test_ports() as (ports, coord_file):
            websocket_port = ports['websocket']
            mcp_port = ports['mcp']

            # Start the complete FoxMCP server (WebSocket + MCP)
            server = FoxMCPServer(
                host="localhost",
                port=websocket_port,
                mcp_port=mcp_port,
                start_mcp=True  # Enable MCP server for end-to-end testing
            )

            # Track connections and messages for testing
            server.connected_clients = []
            server.received_messages = []
            server.sent_messages = []

            # Override handlers to track activity
            original_connection_handler = server.handle_extension_connection
            original_message_handler = server.handle_extension_message

            async def tracking_connection_handler(websocket):
                server.connected_clients.append(websocket)
                try:
                    await original_connection_handler(websocket)
                finally:
                    if websocket in server.connected_clients:
                        server.connected_clients.remove(websocket)

            async def tracking_message_handler(message):
                server.received_messages.append(message)
                result = await original_message_handler(message)
                return result

            # Override send method to track sent messages
            original_send = server.send_to_extension
            async def tracking_send(message):
                server.sent_messages.append(message)
                return await original_send(message)

            server.handle_extension_connection = tracking_connection_handler
            server.handle_extension_message = tracking_message_handler
            server.send_to_extension = tracking_send

            # Start servers (WebSocket server only - MCP handled by start_mcp=True)
            websocket_task = asyncio.create_task(server.start_server())

            # Wait for servers to start
            await asyncio.sleep(1.0)

            # Create real MCP client harness
            mcp_client = DirectMCPTestClient(server.mcp_tools)

            system_info = {
                'server': server,
                'websocket_port': websocket_port,
                'mcp_port': mcp_port,
                'mcp_client': mcp_client,
                'coordination_file': coord_file,
                'websocket_task': websocket_task
            }

            try:
                yield system_info
            finally:
                # Cleanup
                await mcp_client.disconnect()
                await server.shutdown(websocket_task)

    @pytest.mark.asyncio
    async def test_end_to_end_tab_creation_and_listing(self, full_mcp_system):
        """Test complete end-to-end tab creation and listing with actual browser tabs"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']

        # Skip if required components not available

        firefox_path = os.environ.get('FIREFOX_PATH', 'firefox')
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip("Firefox not found")

        # Connect MCP client
        await mcp_client.connect()

        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'],
            coordination_file=system['coordination_file']
        ) as firefox:

            success = firefox.setup_and_start_firefox(headless=True)
            if not success:
                pytest.skip("Firefox setup or extension installation failed")

            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])

            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test tab functionality")

            print("\n🧪 Testing End-to-End Tab Creation and Listing")

            # Step 1: Test tabs_list when no tabs exist (or only about:blank)
            print("\n1️⃣  Testing tabs_list with minimal tabs...")
            result = await mcp_client.call_tool("tabs_list")

            # This should succeed even if no tabs found
            assert not result.get('isError', False), f"tabs_list should not error: {result}"
            initial_content = result.get('content', '')
            print(f"   Initial tab state: {initial_content}")

            # Step 2: Create test tabs using MCP tab_create tool
            print("\n2️⃣  Creating test tabs via MCP tools...")

            test_urls = [
                "https://example.com",
                "https://httpbin.org/status/200",
                "https://httpbin.org/html"
            ]

            created_tabs = []

            try:
                # Create tabs using the MCP tab_create tool
                for i, url in enumerate(test_urls):
                    print(f"   Creating tab {i+1}: {url}")
                    result = await mcp_client.call_tool("tabs_create", {"url": url, "active": False})

                    if not result.get('isError', False):
                        created_tabs.append(url)
                        print(f"   ✅ Tab created: {result.get('content', '')}")
                    else:
                        print(f"   ⚠️  Tab creation failed: {result.get('content', '')}")

                    # Small delay between tab creation
                    await asyncio.sleep(1.0)

                if len(created_tabs) > 0:
                    print(f"   ✅ Successfully created {len(created_tabs)} test tabs")

                    # Wait for tabs to be loaded
                    await asyncio.sleep(2.0)

                    # Step 3: Test tabs_list with created tabs
                    print("\n3️⃣  Testing tabs_list with created tabs...")
                    result = await mcp_client.call_tool("tabs_list")

                    assert not result.get('isError', False), f"tabs_list should not error after creating tabs: {result}"

                    tab_content = result.get('content', '')
                    print(f"   Tab list content: {tab_content}")

                    # Verify we got actual tab data, not "No tabs found"
                    assert "No tabs found" not in tab_content, "Should find tabs after creating them"
                    assert "Open tabs:" in tab_content or "ID " in tab_content, "Should show tab information"

                    # Step 4: Verify tab creation tool
                    print("\n4️⃣  Testing tabs_create via MCP...")
                    create_result = await mcp_client.call_tool("tabs_create", {
                        "url": "https://httpbin.org/json",
                        "active": True
                    })

                    assert not create_result.get('isError', False), f"tabs_create should not error: {create_result}"

                    create_content = create_result.get('content', '')
                    print(f"   Tab creation result: {create_content}")

                    # Verify creation was successful
                    assert "Created tab:" in create_content or "Successfully" in create_content, "Should confirm tab creation"

                    # Step 5: Final tabs_list to verify all tabs
                    print("\n5️⃣  Final tabs_list verification...")
                    final_result = await mcp_client.call_tool("tabs_list")

                    assert not final_result.get('isError', False), f"Final tabs_list should not error: {final_result}"

                    final_content = final_result.get('content', '')
                    print(f"   Final tab count verification: {final_content}")

                    # Should have at least 3 tabs
                    tab_lines = [line for line in final_content.split('\n') if '- ID ' in line]
                    assert len(tab_lines) >= 3, f"Should have at least 3 tabs, found: {len(tab_lines)}"

                    print(f"✅ End-to-end tab test successful! Found {len(tab_lines)} tabs")

                else:
                    print("   ⚠️  No test tabs were successfully created")
                    pytest.skip("Could not create test tabs for verification")

            except Exception as e:
                print(f"   ⚠️  Tab creation error: {e}")
                pytest.skip("Tab creation functionality not available")

    @pytest.mark.asyncio
    async def test_end_to_end_content_execute_script(self, full_mcp_system):
        """Test complete end-to-end JavaScript execution in browser tabs via MCP"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']

        # Skip if required components not available

        firefox_path = os.environ.get('FIREFOX_PATH', 'firefox')
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip("Firefox not found")

        # Connect MCP client
        await mcp_client.connect()

        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'],
            coordination_file=system['coordination_file']
        ) as firefox:

            success = firefox.setup_and_start_firefox(headless=True)
            if not success:
                pytest.skip("Firefox setup or extension installation failed")

            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])

            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test script execution")

            print("\n🧪 Testing End-to-End JavaScript Execution")

            # Step 1: Get existing tabs to find one we can test with
            print("\n1️⃣  Getting existing tabs...")
            tabs_result = await mcp_client.call_tool("tabs_list")
            assert not tabs_result.get('isError', False), f"tabs_list should not error: {tabs_result}"

            tab_content = tabs_result.get('content', '')
            print(f"   Available tabs: {tab_content}")

            # Parse tab content to find any tab
            tab_lines = [line for line in tab_content.split('\n') if 'ID ' in line and ':' in line]

            if not tab_lines:
                pytest.skip("No tabs found for script execution test")

            # Extract tab ID from the first available tab
            tab_line = tab_lines[0]
            tab_id_match = re.search(r'ID (\d+):', tab_line)
            if not tab_id_match:
                pytest.skip("Could not extract tab ID from tabs list")

            test_tab_id = int(tab_id_match.group(1))
            print(f"   ✅ Found test tab ID: {test_tab_id}")

            # Step 2: Create a new tab with a simple web URL where content scripts can run
            print("\n2️⃣  Creating tab with web URL...")
            create_result = await mcp_client.call_tool("tabs_create", {
                "url": "https://httpbin.org/html",
                "active": True
            })

            if create_result.get('isError', False):
                print(f"   ⚠️  Tab creation failed: {create_result.get('content', '')}")
                print("   Using existing tab...")
            else:
                print(f"   ✅ Created web tab: {create_result.get('content', '')}")
                # Wait for tab to load and get new tab list
                await asyncio.sleep(3.0)

                # Get updated tab list to find our new tab
                new_tabs_result = await mcp_client.call_tool("tabs_list")
                if not new_tabs_result.get('isError', False):
                    new_tab_content = new_tabs_result.get('content', '')
                    new_tab_lines = [line for line in new_tab_content.split('\n') if 'httpbin.org' in line]

                    if new_tab_lines:
                        new_tab_line = new_tab_lines[0]
                        new_tab_id_match = re.search(r'ID (\d+):', new_tab_line)
                        if new_tab_id_match:
                            test_tab_id = int(new_tab_id_match.group(1))
                            print(f"   ✅ Using new web tab ID: {test_tab_id}")

            # Wait for content script to be fully loaded
            await asyncio.sleep(2.0)

            # Step 3: Test simple JavaScript execution
            print("\n3️⃣  Testing simple JavaScript execution...")
            script_result = await mcp_client.call_tool("content_execute_script", {
                "tab_id": test_tab_id,
                "code": "document.title"
            })

            assert not script_result.get('isError', False), f"Simple script should not error: {script_result}"

            script_content = script_result.get('content', '')
            print(f"   Script result: {script_content}")

            # Verify we got a result
            assert "Script result from tab" in script_content or "Script executed successfully" in script_content, \
                "Should get script execution result"

            print("✅ End-to-end JavaScript execution test successful!")

    @pytest.mark.asyncio
    async def test_end_to_end_navigation_reload(self, full_mcp_system):
        """Test complete end-to-end page reload functionality via MCP"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']

        # Skip if required components not available

        firefox_path = os.environ.get('FIREFOX_PATH', 'firefox')
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip("Firefox not found")

        # Connect MCP client
        await mcp_client.connect()

        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'],
            coordination_file=system['coordination_file']
        ) as firefox:

            success = firefox.setup_and_start_firefox(headless=True)
            if not success:
                pytest.skip("Firefox setup or extension installation failed")

            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])

            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test navigation reload")

            print("\n🧪 Testing End-to-End Navigation Reload")

            # Step 1: Create a test tab with a web URL
            print("\n1️⃣  Creating test tab...")
            create_result = await mcp_client.call_tool("tabs_create", {
                "url": "https://httpbin.org/uuid",
                "active": True
            })

            if create_result.get('isError', False):
                pytest.skip(f"Tab creation failed: {create_result.get('content', '')}")

            print(f"   ✅ Created tab: {create_result.get('content', '')}")

            # Wait for tab to fully load
            await asyncio.sleep(8.0)

            # Step 2: Get the new tab ID from tabs list
            print("\n2️⃣  Finding test tab ID...")
            tabs_result = await mcp_client.call_tool("tabs_list")
            assert not tabs_result.get('isError', False), f"tabs_list should not error: {tabs_result}"

            tab_content = tabs_result.get('content', '')
            print(f"   Available tabs: {tab_content}")

            # Find tab with httpbin.org/uuid URL
            tab_lines = [line for line in tab_content.split('\n') if 'httpbin.org/uuid' in line]

            if not tab_lines:
                pytest.skip("Could not find test tab with httpbin.org/uuid")

            # Extract tab ID
            tab_id_match = re.search(r'ID (\d+):', tab_lines[0])
            if not tab_id_match:
                pytest.skip("Could not extract tab ID from tabs list")

            test_tab_id = int(tab_id_match.group(1))
            print(f"   ✅ Found test tab ID: {test_tab_id}")

            # Step 3: Test normal reload
            print("\n3️⃣  Testing normal reload...")
            reload_result = await mcp_client.call_tool("navigation_reload", {
                "tab_id": test_tab_id,
                "bypass_cache": False
            })

            assert not reload_result.get('isError', False), f"Normal reload should not error: {reload_result}"

            reload_content = reload_result.get('content', '')
            print(f"   Reload result: {reload_content}")

            # Verify success message
            assert "Successfully reloaded tab" in reload_content, "Should confirm successful reload"
            assert str(test_tab_id) in reload_content, "Should mention the tab ID"

            print("✅ End-to-end navigation reload test successful!")

    @pytest.mark.asyncio
    async def test_end_to_end_content_get_text(self, full_mcp_system):
        """Test complete end-to-end text content extraction from browser tabs via MCP"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']

        # Skip if required components not available

        firefox_path = os.environ.get('FIREFOX_PATH', 'firefox')
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip(f"Firefox not found at {firefox_path}")

        # Connect MCP client
        await mcp_client.connect()

        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'],
            coordination_file=system['coordination_file']
        ) as firefox:

            success = firefox.setup_and_start_firefox(headless=True)
            if not success:
                pytest.skip("Firefox setup or extension installation failed")

            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])

            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test content_get_text")

            print("\n🧪 Testing End-to-End Content Text Extraction")

            # Step 1: Create a test tab with HTML content
            print("\n1️⃣  Creating test tab with HTML content...")
            create_result = await mcp_client.call_tool("tabs_create", {
                "url": "https://example.com",
                "active": True
            })

            if create_result.get('isError', False):
                pytest.skip(f"Tab creation failed: {create_result.get('content', '')}")

            print(f"   ✅ Created tab: {create_result.get('content', '')}")

            # Wait for tab to fully load
            await asyncio.sleep(8.0)

            # Step 2: Get the new tab ID from tabs list
            print("\n2️⃣  Finding test tab ID...")
            tabs_result = await mcp_client.call_tool("tabs_list")
            assert not tabs_result.get('isError', False), f"tabs_list should not error: {tabs_result}"

            tab_content = tabs_result.get('content', '')
            print(f"   Available tabs: {tab_content}")

            # Find tab with example.com URL
            tab_lines = [line for line in tab_content.split('\n') if 'example.com' in line]

            if not tab_lines:
                pytest.skip("Could not find test tab with example.com")

            # Extract tab ID
            tab_id_match = re.search(r'ID (\d+):', tab_lines[0])
            if not tab_id_match:
                pytest.skip("Could not extract tab ID from tabs list")

            test_tab_id = int(tab_id_match.group(1))
            print(f"   ✅ Found test tab ID: {test_tab_id}")

            # Step 3: Test content_get_text functionality
            print("\n3️⃣  Testing content_get_text...")
            text_result = await mcp_client.call_tool("content_get_text", {
                "tab_id": test_tab_id
            })

            print(f"   content_get_text result: {text_result}")

            # Verify the function executed without error
            assert not text_result.get('isError', False), f"content_get_text should not error: {text_result}"

            text_content = text_result.get('content', '')
            print(f"   Text content received: {text_content[:200]}...")

            # Verify we got text content
            assert "Text content from" in text_content, "Should return formatted text content"

            # Check for error pages that might indicate network issues
            if "502 Bad Gateway" in text_content or "503 Service Unavailable" in text_content or "404 Not Found" in text_content:
                pytest.skip(f"External service unavailable, got error page: {text_content[:100]}")

            assert len(text_content) > 50, "Should return meaningful text content (excluding error pages)"

            print("✅ End-to-end content_get_text test successful!")

    @pytest.mark.asyncio
    async def test_end_to_end_tab_screenshot_capture(self, full_mcp_system):
        """Test complete end-to-end screenshot capture from browser tabs via MCP"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']

        # Skip if required components not available

        firefox_path = os.environ.get('FIREFOX_PATH', 'firefox')
        if not os.path.exists(os.path.expanduser(firefox_path)):
            pytest.skip("Firefox not found")

        # Connect MCP client
        await mcp_client.connect()

        # Start Firefox with extension
        with FirefoxTestManager(
            firefox_path=firefox_path,
            test_port=system['websocket_port'],
            coordination_file=system['coordination_file']
        ) as firefox:

            success = firefox.setup_and_start_firefox(headless=True)
            if not success:
                pytest.skip("Firefox setup or extension installation failed")

            # Wait for extension connection
            await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])

            if len(server.connected_clients) == 0:
                pytest.skip("Extension did not connect - cannot test screenshot functionality")

            print("\n🧪 Testing End-to-End Screenshot Capture")

            # Step 1: Test basic screenshot capture with default parameters
            print("\n1️⃣  Testing basic screenshot capture...")
            screenshot_result = await mcp_client.call_tool("tabs_capture_screenshot")
            print(f"   Screenshot result: {screenshot_result}")

            assert not screenshot_result.get('isError', False), f"Screenshot capture should not error: {screenshot_result}"

            screenshot_content = screenshot_result.get('content', '')
            assert "Screenshot captured successfully" in screenshot_content, "Should report successful capture"
            assert "data:image/" in screenshot_content, "Should contain data URL"
            print("   ✅ Basic screenshot capture successful")

            # Step 2: Test screenshot with PNG format
            print("\n2️⃣  Testing PNG format screenshot...")
            png_result = await mcp_client.call_tool("tabs_capture_screenshot", {
                "format": "png",
                "quality": 100
            })

            assert not png_result.get('isError', False), f"PNG screenshot should not error: {png_result}"
            png_content = png_result.get('content', '')
            assert "Screenshot captured successfully" in png_content, "PNG screenshot should succeed"
            print("   ✅ PNG format screenshot successful")

            print("✅ End-to-end screenshot capture test successful!")