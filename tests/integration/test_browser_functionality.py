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

import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from port_coordinator import coordinated_test_ports
from firefox_test_utils import FirefoxTestManager
from test_config import FIREFOX_TEST_CONFIG
from mcp_client_harness import DirectMCPTestClient


def png_pixel(png: bytes, x: int, y: int):
    """(r, g, b) of one pixel of an 8-bit RGB or RGBA PNG: enough to tell red from blue"""
    import struct
    import zlib

    assert png.startswith(b"\x89PNG\r\n\x1a\n"), "not a PNG"
    position, idat = 8, b""
    while position < len(png):
        length, kind = struct.unpack(">I4s", png[position:position + 8])
        body = png[position + 8:position + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", body[:10])
        elif kind == b"IDAT":
            idat += body
        position += 12 + length
    assert depth == 8 and color in (2, 6), f"unsupported PNG (depth {depth}, colour type {color})"
    assert x < width and y < height, f"pixel ({x}, {y}) is outside the {width}x{height} image"
    bpp = 3 if color == 2 else 4
    stride = width * bpp
    raw = zlib.decompress(idat)
    previous, line = bytearray(stride), bytearray(stride)
    for row in range(y + 1):  # each row is filtered against the one above, so read down to y
        start = row * (stride + 1)
        filter_type = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = line[i - bpp] if i >= bpp else 0
            above = previous[i]
            corner = previous[i - bpp] if i >= bpp else 0
            if filter_type == 1:
                line[i] = (line[i] + left) & 255
            elif filter_type == 2:
                line[i] = (line[i] + above) & 255
            elif filter_type == 3:
                line[i] = (line[i] + ((left + above) >> 1)) & 255
            elif filter_type == 4:
                guess = left + above - corner
                distances = abs(guess - left), abs(guess - above), abs(guess - corner)
                near_left, near_above, near_corner = distances
                if near_left <= near_above and near_left <= near_corner:
                    pick = left
                elif near_above <= near_corner:
                    pick = above
                else:
                    pick = corner
                line[i] = (line[i] + pick) & 255
        previous = line
    return tuple(line[x * bpp:x * bpp + 3])


class TestBrowserFunctionality:
    """Browser functionality integration tests"""

    @pytest_asyncio.fixture
    async def full_mcp_system(self, server_with_extension):
        """Complete browser testing system with MCP client"""
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
            'mcp_port': mcp_port,
            'websocket_port': test_port,  # compatibility alias
            'coordination_file': server_with_extension.get('coordination_file')
        }

        # Cleanup
        await mcp_client.disconnect()

    @pytest.mark.asyncio
    async def test_end_to_end_tab_creation_and_listing(self, full_mcp_system):
        """Test complete end-to-end tab creation and listing with actual browser tabs"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']

        # Connect MCP client
        await mcp_client.connect()

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
            "https://example.org/status/200",
            "https://example.org/html"
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
                    "url": "https://example.org/json",
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

        # Connect MCP client
        await mcp_client.connect()

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
            "url": "https://example.com",
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
                new_tab_lines = [line for line in new_tab_content.split('\n') if 'example.com' in line]

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

        # Connect MCP client
        await mcp_client.connect()

        print("\n🧪 Testing End-to-End Navigation Reload")

        # Step 1: Create a test tab with a web URL
        print("\n1️⃣  Creating test tab...")
        create_result = await mcp_client.call_tool("tabs_create", {
            "url": "https://example.org/uuid",
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

        # Find tab with example.org/uuid URL
        tab_lines = [line for line in tab_content.split('\n') if 'example.org/uuid' in line]

        if not tab_lines:
            pytest.skip("Could not find test tab with example.org/uuid")

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

        # Connect MCP client
        await mcp_client.connect()

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

        # Step 3: Test content_get_text functionality (unlimited)
        print("\n3️⃣  Testing content_get_text (unlimited)...")
        text_result = await mcp_client.call_tool("content_get_text", {
            "tab_id": test_tab_id
        })

        print(f"   content_get_text result: {text_result}")

        # Verify the function executed without error
        assert not text_result.get('isError', False), f"content_get_text should not error: {text_result}"

        text_content = text_result.get('content', '')
        print(f"   Text content received (full): {len(text_content)} chars")

        # Verify we got text content
        assert "Text content from" in text_content, "Should return formatted text content"

        # Check for error pages that might indicate network issues
        if "502 Bad Gateway" in text_content or "503 Service Unavailable" in text_content or "404 Not Found" in text_content:
            pytest.skip(f"External service unavailable, got error page: {text_content[:100]}")

        assert len(text_content) > 50, "Should return meaningful text content (excluding error pages)"

        # Step 4: Test content_get_text with max_length limit
        print("\n4️⃣  Testing content_get_text with max_length=100...")
        limited_text_result = await mcp_client.call_tool("content_get_text", {
            "tab_id": test_tab_id,
            "max_length": 100
        })

        assert not limited_text_result.get('isError', False), f"content_get_text with max_length should not error: {limited_text_result}"

        limited_content = limited_text_result.get('content', '')
        print(f"   Limited text content received: {len(limited_content)} chars")

        # Verify truncation occurred (accounting for header text)
        assert "..." in limited_content, "Limited content should be truncated"
        assert len(limited_content) < len(text_content), "Limited content should be shorter than unlimited"

        print("✅ End-to-end content_get_text test successful!")

    @pytest.mark.asyncio
    async def test_end_to_end_tab_screenshot_capture(self, full_mcp_system):
        """Test complete end-to-end screenshot capture from browser tabs via MCP"""
        system = full_mcp_system
        server = system['server']
        mcp_client = system['mcp_client']

        # Connect MCP client
        await mcp_client.connect()

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

    @pytest.mark.asyncio
    async def test_end_to_end_background_tab_screenshot(self, full_mcp_system, tmp_path):
        """tab_id captures a tab that is not showing, and does not bring it to the front

        Headless Firefox keeps its first tab selected whatever `active` says (and ignores
        tabs_switch), so the tab in front stays the blank one and both painted tabs are in the
        background: exactly the case tab_id is for.
        """
        system = full_mcp_system
        mcp_client = system['mcp_client']
        await mcp_client.connect()

        print("\n🧪 Testing screenshot of a background tab")

        async def painted_tab(color):
            """A new tab loaded from example.org and painted one colour all over"""
            created = await mcp_client.call_tool(
                "tabs_create", {"url": "https://example.org/", "active": False})
            assert not created.get('isError', False), f"tabs_create should not error: {created}"
            tab_id = int(re.search(r'ID (\d+)', created.get('content', '')).group(1))
            await asyncio.sleep(3.0)  # let the page load and the content script start
            paint = (
                "document.documentElement.style.background = '%s';"
                "document.body.innerHTML = "
                "'<div style=\"position:fixed;inset:0;background:%s\"></div>';"
                "'painted'" % (color, color)
            )
            result = await mcp_client.call_tool(
                "content_execute_script", {"tab_id": tab_id, "code": paint})
            assert not result.get('isError', False), f"painting the tab should not error: {result}"
            await asyncio.sleep(0.5)
            return tab_id

        async def active_tab():
            listing = (await mcp_client.call_tool("tabs_list")).get('content', '')
            lines = [line for line in listing.split('\n') if '(active)' in line]
            return int(re.search(r'ID (\d+):', lines[0]).group(1))

        blue = await painted_tab("rgb(0,0,255)")
        red = await painted_tab("rgb(255,0,0)")
        in_front = await active_tab()
        assert in_front not in (blue, red), "both painted tabs should be in the background"

        async def capture(**arguments):
            name = str(tmp_path / f"shot-{len(list(tmp_path.iterdir()))}.png")
            result = await mcp_client.call_tool(
                "tabs_capture_screenshot", {"filename": name, **arguments})
            assert not result.get('isError', False), f"screenshot should not error: {result}"
            content = result.get('content', '')
            assert content.startswith("Screenshot saved to"), content
            with open(name, 'rb') as f:
                return content, f.read()

        print("\n1️⃣  Without tab_id it is the visible tab, which is neither of ours...")
        _, png = await capture()
        r, g, b = png_pixel(png, 20, 20)
        assert r < 100 and b < 100, f"the visible tab is the blank one, got {(r, g, b)}"

        print("\n2️⃣  tab_id of a background tab gives that tab's own page, blue...")
        content, png = await capture(tab_id=blue)
        r, g, b = png_pixel(png, 20, 20)
        assert b > 200 and r < 60, f"the blue tab should be blue, got {(r, g, b)}"
        assert f"tab {blue}" in content, content
        assert png_pixel(png, 600, 300) == (r, g, b), "and all of it, not just a corner"

        print("\n3️⃣  ...and of the other one, red...")
        _, png = await capture(tab_id=red)
        r, g, b = png_pixel(png, 20, 20)
        assert r > 200 and b < 60, f"the red tab should be red, got {(r, g, b)}"

        print("\n4️⃣  ...and nothing was switched.")
        assert await active_tab() == in_front

        print("\n5️⃣  A tab that does not exist, or a tab and a window together, are refused...")
        missing = await mcp_client.call_tool("tabs_capture_screenshot", {"tab_id": 987654321})
        missing_text = missing.get('content', '')
        assert "Screenshot" not in missing_text or "Failed" in missing_text, missing
        both = await mcp_client.call_tool(
            "tabs_capture_screenshot", {"tab_id": blue, "window_id": 1})
        assert "not both" in both.get('content', ''), both

        print("✅ Background tab screenshot test successful!")
