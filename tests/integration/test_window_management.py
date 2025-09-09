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
        mcp_port = setup['mcp_port']
        
        print(f"Testing window listing via MCP on port {mcp_port}")
        
        # Create MCP client
        client = DirectMCPTestClient("localhost", mcp_port)
        
        try:
            # Test list_windows tool
            result = await client.call_tool("list_windows", {"populate": True})
            
            # Validate response structure
            assert isinstance(result, dict), "Result should be a dict"
            assert "windows" in result, "Result should contain 'windows' key"
            assert isinstance(result["windows"], list), "Windows should be a list"
            assert len(result["windows"]) > 0, "Should have at least one window"
            
            # Check window structure
            window = result["windows"][0]
            assert "id" in window, "Window should have an id"
            assert "type" in window, "Window should have a type"
            assert "state" in window, "Window should have a state"
            assert "focused" in window, "Window should have focused status"
            assert "tabs" in window, "Window should have tabs (populate=True)"
            
            print(f"Found {len(result['windows'])} window(s)")
            
        finally:
            await client.cleanup()

    @pytest.mark.asyncio
    async def test_get_current_window(self, server_with_extension):
        """Test getting current window information"""
        setup = server_with_extension
        mcp_port = setup['mcp_port']
        
        # Create MCP client
        client = DirectMCPTestClient("localhost", mcp_port)
        
        try:
            # Test get_current_window tool
            result = await client.call_tool("get_current_window", {"populate": True})
            
            # Validate response
            assert isinstance(result, dict), "Result should be a dict"
            assert "window" in result, "Result should contain 'window' key"
            
            window = result["window"]
            assert "id" in window, "Window should have an id"
            assert "type" in window, "Window should have a type"
            assert "focused" in window, "Window should have focused status"
            assert window["focused"] == True, "Current window should be focused"
            
            print(f"Current window ID: {window['id']}")
            
        finally:
            await client.cleanup()

    @pytest.mark.asyncio
    async def test_create_and_close_window(self, server_with_extension):
        """Test creating and closing a window"""
        setup = server_with_extension
        mcp_port = setup['mcp_port']
        
        # Create MCP client
        client = DirectMCPTestClient("localhost", mcp_port)
        
        try:
            # Get initial window count
            initial_windows = await client.call_tool("list_windows", {"populate": False})
            initial_count = len(initial_windows["windows"])
            
            # Create new window
            create_result = await client.call_tool("create_window", {
                "url": "about:blank",
                "window_type": "normal",
                "width": 800,
                "height": 600,
                "focused": True
            })
            
            # Validate creation
            assert "window" in create_result, "Create result should contain window"
            new_window = create_result["window"]
            assert "id" in new_window, "New window should have an id"
            new_window_id = new_window["id"]
            
            # Wait for window to be created
            await asyncio.sleep(1.0)
            
            # Verify window was created
            after_create_windows = await client.call_tool("list_windows", {"populate": False})
            assert len(after_create_windows["windows"]) == initial_count + 1, "Should have one more window"
            
            print(f"Created window with ID: {new_window_id}")
            
            # Close the window
            close_result = await client.call_tool("close_window", {"window_id": new_window_id})
            
            # Validate closure
            assert close_result.get("success") == True, "Window should close successfully"
            
            # Wait for window to be closed
            await asyncio.sleep(1.0)
            
            # Verify window was closed
            after_close_windows = await client.call_tool("list_windows", {"populate": False})
            assert len(after_close_windows["windows"]) == initial_count, "Should be back to original count"
            
            print(f"Closed window with ID: {new_window_id}")
            
        finally:
            await client.cleanup()

    @pytest.mark.asyncio
    async def test_focus_window(self, server_with_extension):
        """Test focusing a window"""
        setup = server_with_extension
        mcp_port = setup['mcp_port']
        
        # Create MCP client
        client = DirectMCPTestClient("localhost", mcp_port)
        
        try:
            # Get current window
            current_result = await client.call_tool("get_current_window", {"populate": False})
            current_window_id = current_result["window"]["id"]
            
            # Focus the current window (should always succeed)
            focus_result = await client.call_tool("focus_window", {"window_id": current_window_id})
            
            # Validate focus
            assert focus_result.get("success") == True, "Focus should succeed"
            assert focus_result.get("windowId") == current_window_id, "Should return window ID"
            
            print(f"Successfully focused window ID: {current_window_id}")
            
        finally:
            await client.cleanup()

    @pytest.mark.asyncio
    async def test_get_window_by_id(self, server_with_extension):
        """Test getting specific window by ID"""
        setup = server_with_extension
        mcp_port = setup['mcp_port']
        
        # Create MCP client
        client = DirectMCPTestClient("localhost", mcp_port)
        
        try:
            # Get current window ID
            current_result = await client.call_tool("get_current_window", {"populate": False})
            window_id = current_result["window"]["id"]
            
            # Get window by ID
            get_result = await client.call_tool("get_window", {
                "window_id": window_id,
                "populate": True
            })
            
            # Validate result
            assert "window" in get_result, "Result should contain window"
            window = get_result["window"]
            assert window["id"] == window_id, "Should return correct window"
            assert "tabs" in window, "Should include tabs (populate=True)"
            
            print(f"Retrieved window ID: {window_id} with {len(window.get('tabs', []))} tabs")
            
        finally:
            await client.cleanup()

    @pytest.mark.asyncio
    async def test_update_window_properties(self, server_with_extension):
        """Test updating window properties"""
        setup = server_with_extension
        mcp_port = setup['mcp_port']
        
        # Create MCP client
        client = DirectMCPTestClient("localhost", mcp_port)
        
        try:
            # Get current window
            current_result = await client.call_tool("get_current_window", {"populate": False})
            window_id = current_result["window"]["id"]
            original_state = current_result["window"].get("state", "normal")
            
            # Try to update window (resize it)
            update_result = await client.call_tool("update_window", {
                "window_id": window_id,
                "width": 900,
                "height": 700,
                "focused": True
            })
            
            # Validate update
            assert "window" in update_result, "Update result should contain window"
            updated_window = update_result["window"]
            assert updated_window["id"] == window_id, "Should return same window ID"
            
            # Note: Some properties might not change due to Firefox restrictions,
            # but the operation should still succeed
            print(f"Updated window ID: {window_id}")
            
        finally:
            await client.cleanup()

    @pytest.mark.asyncio  
    async def test_window_error_handling(self, server_with_extension):
        """Test error handling for invalid window operations"""
        setup = server_with_extension
        mcp_port = setup['mcp_port']
        
        # Create MCP client
        client = DirectMCPTestClient("localhost", mcp_port)
        
        try:
            # Try to get non-existent window
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("get_window", {"window_id": 99999, "populate": False})
            
            # The error should contain window not found information
            error_str = str(exc_info.value).lower()
            assert "window" in error_str or "not found" in error_str, "Should indicate window not found"
            
            # Try to close non-existent window
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("close_window", {"window_id": 99999})
                
            error_str = str(exc_info.value).lower()
            assert "window" in error_str or "not found" in error_str, "Should indicate window not found"
            
            print("Error handling tests passed")
            
        finally:
            await client.cleanup()


if __name__ == "__main__":
    # Run tests individually for debugging
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        asyncio.run(test_debug())
    else:
        pytest.main([__file__, "-v", "-s"])