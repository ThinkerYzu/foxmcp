"""
Window Management End-to-End Tests

Comprehensive functional tests for browser window operations through the
MCP server and WebSocket protocol with real Firefox extension.
"""

import pytest
import pytest_asyncio
import asyncio
import json
import sys
import os
from datetime import datetime, timedelta

# Add the parent directory to the path to import server module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from server.server import FoxMCPServer

# Import test utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from ..test_config import TEST_PORTS, FIREFOX_TEST_CONFIG
    from ..firefox_test_utils import FirefoxTestManager, get_extension_xpi_path
    from ..port_coordinator import coordinated_test_ports
    from ..mcp_client_harness import DirectMCPTestClient
except ImportError:
    from test_config import TEST_PORTS, FIREFOX_TEST_CONFIG
    from firefox_test_utils import FirefoxTestManager, get_extension_xpi_path
    from port_coordinator import coordinated_test_ports
    from mcp_client_harness import DirectMCPTestClient


class TestWindowManagementEndToEnd:
    """End-to-end tests for window management functionality"""
    
    @pytest_asyncio.fixture
    async def server_with_extension(self):
        """Start server and Firefox extension for window testing"""
        # Use dynamic port allocation
        with coordinated_test_ports() as (ports, coord_file):
            test_port = ports['websocket']
            mcp_port = ports['mcp']
            
            # Get extension XPI
            extension_xpi = get_extension_xpi_path()
            if not extension_xpi or not os.path.exists(extension_xpi):
                pytest.skip("Extension XPI not found. Run 'make package' first.")
            
            # Create server
            server = FoxMCPServer(
                host="localhost",
                port=test_port,
                mcp_port=mcp_port,
                start_mcp=True
            )
            
            # Start Firefox with extension
            firefox_path = os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')
            firefox = FirefoxTestManager(
                firefox_path=firefox_path,
                test_port=test_port,
                coordination_file=coord_file
            )
            
            try:
                # Create profile and install extension
                firefox.create_test_profile()
                success = firefox.install_extension(extension_xpi)
                if not success:
                    pytest.skip("Extension installation failed")
                
                # Start Firefox
                firefox_started = firefox.start_firefox(headless=True)
                if not firefox_started:
                    pytest.skip("Firefox startup failed")
                
                # Start server
                server_task = asyncio.create_task(server.start_server())
                await asyncio.sleep(0.5)  # Give server time to start
                
                # Give Firefox and extension time to connect
                await asyncio.sleep(3.0)
                
                yield {
                    'server': server,
                    'firefox': firefox,
                    'test_port': test_port,
                    'mcp_port': mcp_port,
                    'ports': ports
                }
                
            finally:
                # Clean up
                try:
                    if firefox:
                        firefox.cleanup()
                except Exception as e:
                    print(f"Firefox cleanup error: {e}")
                
                try:
                    server_task.cancel()
                    await server_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"Server cleanup error: {e}")

    @pytest.mark.asyncio
    async def test_list_windows(self, server_with_extension):
        """Test listing all browser windows"""
        setup = server_with_extension
        
        # Create MCP client
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()
        
        try:
            # Test list_windows tool
            result = await client.call_tool("list_windows", {"populate": True})
            
            # Extract content from MCP client wrapper
            assert isinstance(result, dict), "MCP client should return dict wrapper"
            assert result.get("success", False), "Tool call should succeed"
            content = result.get("content", "")
            
            # Validate response content
            assert isinstance(content, str), "Content should be a string"
            assert "Browser windows" in content, "Result should contain 'Browser windows'"
            assert "found" in content, "Result should show count of windows found"
            
            # Check for window information in the response
            assert "ID" in content, "Window should have an ID"
            assert "window" in content, "Should indicate window type"
            
            print(f"Window list result: {content[:200]}...")
            
        finally:
            pass

    @pytest.mark.asyncio
    async def test_get_current_window(self, server_with_extension):
        """Test getting current window information"""
        setup = server_with_extension
        
        # Create MCP client
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()
        
        try:
            # Test get_current_window tool
            result = await client.call_tool("get_current_window", {"populate": True})
            
            # Extract content from MCP client wrapper
            assert isinstance(result, dict), "MCP client should return dict wrapper"
            assert result.get("success", False), "Tool call should succeed"
            content = result.get("content", "")
            
            # Validate response
            assert isinstance(content, str), "Content should be a string"
            assert "Current window" in content, "Result should contain 'Current window'"
            assert "ID" in content, "Window should have an ID"
            
            print(f"Current window result: {content}")
            
        finally:
            pass

    @pytest.mark.asyncio
    async def test_create_and_close_window(self, server_with_extension):
        """Test creating and closing a window"""
        setup = server_with_extension
        
        # Create MCP client
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()
        
        try:
            # Get initial window count  
            initial_windows = await client.call_tool("list_windows", {"populate": False})
            # Extract content from MCP client wrapper
            initial_content = initial_windows.get("content", "")
            # Extract window count from string response like "Browser windows (2 found):"
            import re
            count_match = re.search(r'Browser windows \((\d+) found\)', initial_content)
            initial_count = int(count_match.group(1)) if count_match else 0
            
            # Create new window
            create_result = await client.call_tool("create_window", {
                "url": "about:blank",
                "window_type": "normal",
                "width": 800,
                "height": 600,
                "focused": True
            })
            
            # Extract content from MCP client wrapper
            create_content = create_result.get("content", "")
            
            # Validate creation
            assert isinstance(create_content, str), "Create result should be a string"
            assert "Created" in create_content, "Result should indicate creation"
            assert "ID" in create_content, "Result should contain window ID"
            
            # Extract window ID from result like "Created normal window (ID 123): ..."
            import re
            id_match = re.search(r'ID (\d+)', create_content)
            assert id_match, f"Could not extract window ID from: {create_content}"
            new_window_id = int(id_match.group(1))
            
            # Wait for window to be created
            await asyncio.sleep(1.0)
            
            # Verify window was created
            after_create_windows = await client.call_tool("list_windows", {"populate": False})
            after_create_content = after_create_windows.get("content", "")
            count_match = re.search(r'Browser windows \((\d+) found\)', after_create_content)
            after_create_count = int(count_match.group(1)) if count_match else 0
            assert after_create_count == initial_count + 1, "Should have one more window"
            
            print(f"Created window with ID: {new_window_id}")
            
            # Close the window
            close_result = await client.call_tool("close_window", {"window_id": new_window_id})
            
            # Extract content and validate closure
            close_content = close_result.get("content", "")
            assert isinstance(close_content, str), "Close result should be a string"
            assert "closed successfully" in close_content, "Window should close successfully"
            
            # Wait for window to be closed
            await asyncio.sleep(1.0)
            
            # Verify window was closed
            after_close_windows = await client.call_tool("list_windows", {"populate": False})
            after_close_content = after_close_windows.get("content", "")
            count_match = re.search(r'Browser windows \((\d+) found\)', after_close_content)
            after_close_count = int(count_match.group(1)) if count_match else 0
            assert after_close_count == initial_count, "Should be back to original count"
            
            print(f"Closed window with ID: {new_window_id}")
            
        finally:
            pass

    @pytest.mark.asyncio
    async def test_focus_window(self, server_with_extension):
        """Test focusing a window"""
        setup = server_with_extension
        
        # Create MCP client
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()
        
        try:
            # Get current window
            current_result = await client.call_tool("get_current_window", {"populate": False})
            current_content = current_result.get("content", "")
            
            # Extract window ID from current window result
            import re
            id_match = re.search(r'ID (\d+)', current_content)
            assert id_match, f"Could not extract window ID from: {current_content}"
            current_window_id = int(id_match.group(1))
            
            # Focus the current window (should always succeed)
            focus_result = await client.call_tool("focus_window", {"window_id": current_window_id})
            
            # Extract content and validate focus
            focus_content = focus_result.get("content", "")
            assert isinstance(focus_content, str), "Focus result should be a string"
            assert "focused successfully" in focus_content, "Focus should succeed"
            
            print(f"Successfully focused window ID: {current_window_id}")
            
        finally:
            pass

    @pytest.mark.asyncio
    async def test_get_window_by_id(self, server_with_extension):
        """Test getting specific window by ID"""
        setup = server_with_extension
        
        # Create MCP client
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()
        
        try:
            # Get current window ID
            current_result = await client.call_tool("get_current_window", {"populate": False})
            current_content = current_result.get("content", "")
            
            # Extract window ID from current window result
            import re
            id_match = re.search(r'ID (\d+)', current_content)
            assert id_match, f"Could not extract window ID from: {current_content}"
            window_id = int(id_match.group(1))
            
            # Get window by ID
            get_result = await client.call_tool("get_window", {
                "window_id": window_id,
                "populate": True
            })
            
            # Extract content and validate result
            get_content = get_result.get("content", "")
            assert isinstance(get_content, str), "Get result should be a string"
            assert f"Window {window_id}" in get_content, "Should return correct window"
            assert "tabs" in get_content, "Should mention tabs (populate=True)"
            
            print(f"Retrieved window ID: {window_id}, result: {get_content}")
            
        finally:
            pass

    @pytest.mark.asyncio
    async def test_update_window_properties(self, server_with_extension):
        """Test updating window properties"""
        setup = server_with_extension
        
        # Create MCP client
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()
        
        try:
            # Get current window
            current_result = await client.call_tool("get_current_window", {"populate": False})
            current_content = current_result.get("content", "")
            
            # Extract window ID from current window result
            import re
            id_match = re.search(r'ID (\d+)', current_content)
            assert id_match, f"Could not extract window ID from: {current_content}"
            window_id = int(id_match.group(1))
            
            # Try to update window (resize it)
            update_result = await client.call_tool("update_window", {
                "window_id": window_id,
                "width": 900,
                "height": 700,
                "focused": True
            })
            
            # Extract content and validate update
            update_content = update_result.get("content", "")
            assert isinstance(update_content, str), "Update result should be a string"
            assert f"window {window_id}" in update_content or f"Window {window_id}" in update_content, "Should reference correct window ID"
            
            # Note: Some properties might not change due to Firefox restrictions,
            # but the operation should still succeed
            print(f"Updated window ID: {window_id}, result: {update_content}")
            
        finally:
            pass

    @pytest.mark.asyncio  
    async def test_window_error_handling(self, server_with_extension):
        """Test error handling for invalid window operations"""
        setup = server_with_extension
        
        # Create MCP client
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()
        
        try:
            # Try to get non-existent window
            get_result = await client.call_tool("get_window", {"window_id": 99999, "populate": False})
            get_content = get_result.get("content", "")
            
            # The error should be in the content, not raised as exception
            assert isinstance(get_content, str), "Get result should be a string"
            assert ("Error" in get_content or "not found" in get_content or 
                    "Unable to retrieve" in get_content), "Should indicate error or inability to retrieve"
            
            # Try to close non-existent window  
            close_result = await client.call_tool("close_window", {"window_id": 99999})
            close_content = close_result.get("content", "")
                
            assert isinstance(close_content, str), "Close result should be a string"
            assert ("Error" in close_content or "not found" in close_content or 
                    "Unable to close" in close_content or "Failed to close" in close_content), "Should indicate error or failure to close"
            
            print("Error handling tests passed")
            
        finally:
            pass


if __name__ == "__main__":
    # Run tests individually for debugging
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        asyncio.run(test_debug())
    else:
        pytest.main([__file__, "-v", "-s"])