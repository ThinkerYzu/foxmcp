"""
UI Storage Synchronization Tests using Test Helper Protocol

Tests that verify popup and options pages display correct values from storage.sync
using the WebSocket test helper protocol instead of browser automation.
"""

import pytest
import pytest_asyncio
import asyncio
import json
import sys
import os

# Add the parent directory to the path to import server module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from server.server import FoxMCPServer

# Import test utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from ..test_config import TEST_PORTS, FIREFOX_TEST_CONFIG
    from ..firefox_test_utils import FirefoxTestManager
    from ..port_coordinator import coordinated_test_ports
except ImportError:
    from test_config import TEST_PORTS, FIREFOX_TEST_CONFIG
    from firefox_test_utils import FirefoxTestManager
    from port_coordinator import coordinated_test_ports


class TestUIStorageSync:
    """Test UI synchronization with storage using test helper protocol"""
    
    @pytest_asyncio.fixture
    async def server_with_extension(self):
        """Start server and Firefox extension with test configuration"""
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
                
                # Wait for extension to load configuration and connect automatically
                await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])

                # Wait for extension to connect automatically
                if not server.extension_connection:
                    print("⏳ Extension hasn't connected yet, waiting...")
                    # Wait up to 15 seconds for extension to connect
                    for i in range(30):  # 30 * 0.5s = 15s total
                        await asyncio.sleep(0.5)
                        if server.extension_connection:
                            break
                    else:
                        pytest.skip("Extension did not connect to server")

                # Verify connection
                if not server.extension_connection:
                    pytest.skip("Extension did not connect to server")
                
                yield server, firefox, test_port
                
            finally:
                # Cleanup
                firefox.cleanup()
                await server.shutdown(server_task)
    
    @pytest.mark.asyncio
    async def test_get_popup_state(self, server_with_extension):
        """Test getting popup display state via test helper protocol"""
        server, firefox, test_port = server_with_extension
        
        # Get popup state
        popup_state = await server.get_popup_state()
        
        # Verify response structure
        assert "error" not in popup_state, f"Error getting popup state: {popup_state.get('error')}"
        assert "serverUrl" in popup_state
        assert "hasTestOverrides" in popup_state
        assert "effectiveHostname" in popup_state
        assert "effectivePort" in popup_state
        assert "storageValues" in popup_state
        
        # Verify test port is being used
        assert popup_state["effectivePort"] == test_port
        assert popup_state["hasTestOverrides"] == True
        assert popup_state["testIndicatorShown"] == True
        assert f":{test_port}" in popup_state["serverUrl"]
        
        print(f"✓ Popup state correctly shows test port {test_port}")
    
    @pytest.mark.asyncio
    async def test_get_options_state(self, server_with_extension):
        """Test getting options page display state via test helper protocol"""
        server, firefox, test_port = server_with_extension
        
        # Get options state
        options_state = await server.get_options_state()
        
        # Verify response structure
        assert "error" not in options_state, f"Error getting options state: {options_state.get('error')}"
        assert "displayHostname" in options_state
        assert "displayPort" in options_state
        assert "webSocketUrl" in options_state
        assert "hasTestOverrides" in options_state
        assert "testOverrideWarningShown" in options_state
        
        # Verify test port is displayed
        assert options_state["displayPort"] == test_port
        assert options_state["hasTestOverrides"] == True
        assert options_state["testOverrideWarningShown"] == True
        assert f":{test_port}" in options_state["webSocketUrl"]
        
        print(f"✓ Options state correctly shows test port {test_port}")
    
    @pytest.mark.asyncio
    async def test_get_storage_values(self, server_with_extension):
        """Test getting raw storage values via test helper protocol"""
        server, firefox, test_port = server_with_extension
        
        # Get storage values
        storage_values = await server.get_storage_values()
        
        # Verify response structure
        assert "error" not in storage_values, f"Error getting storage values: {storage_values.get('error')}"
        assert "hostname" in storage_values
        assert "port" in storage_values
        assert "testPort" in storage_values
        assert "testHostname" in storage_values
        
        # Verify test configuration is in storage
        assert storage_values["testPort"] == test_port
        assert storage_values["testHostname"] == "localhost"
        
        print(f"✓ Storage contains test configuration: testPort={test_port}")
    
    @pytest.mark.asyncio 
    async def test_validate_ui_sync(self, server_with_extension):
        """Test validating UI-storage synchronization"""
        server, firefox, test_port = server_with_extension
        
        # Define expected values
        expected_values = {
            "testPort": test_port,
            "testHostname": "localhost",
            "hostname": "localhost"
        }
        
        # Validate UI sync
        validation_result = await server.validate_ui_sync(expected_values)
        
        # Verify response structure
        assert "error" not in validation_result, f"Validation error: {validation_result.get('error')}"
        assert "popupSyncValid" in validation_result
        assert "optionsSyncValid" in validation_result
        assert "storageMatches" in validation_result
        assert "effectiveValues" in validation_result
        assert "issues" in validation_result
        
        # Verify validation passes
        assert validation_result["popupSyncValid"] == True, f"Popup sync invalid: {validation_result.get('issues')}"
        assert validation_result["optionsSyncValid"] == True, f"Options sync invalid: {validation_result.get('issues')}"
        assert validation_result["storageMatches"] == True, f"Storage mismatch: {validation_result.get('issues')}"
        
        # Verify effective values
        assert validation_result["effectiveValues"]["port"] == test_port
        assert validation_result["effectiveValues"]["hostname"] == "localhost"
        
        # Should have no issues
        assert len(validation_result["issues"]) == 0, f"Validation issues: {validation_result['issues']}"
        
        print(f"✓ UI-storage sync validation passed for test port {test_port}")
    
    @pytest.mark.asyncio
    async def test_complete_storage_sync_workflow(self, server_with_extension):
        """Test complete storage sync workflow using test helper"""
        server, firefox, test_port = server_with_extension
        
        # Define test values to validate
        test_values = {
            "testPort": test_port,
            "testHostname": "localhost",
            "retryInterval": 1000,
            "maxRetries": 5,
            "pingTimeout": 2000
        }
        
        # Run complete workflow
        workflow_result = await server.test_storage_sync_workflow(test_values)
        
        # Verify workflow succeeded
        assert "errors" not in workflow_result or len(workflow_result["errors"]) == 0, f"Workflow errors: {workflow_result.get('errors')}"
        assert workflow_result.get("workflow_success") == True, f"Workflow failed: {workflow_result.get('errors')}"
        
        # Verify all steps completed
        steps = workflow_result.get("steps", {})
        assert "initial_storage" in steps
        assert "popup_state" in steps  
        assert "options_state" in steps
        assert "validation" in steps
        
        # Verify validation step passed
        validation = steps["validation"]
        assert validation.get("popupSyncValid") == True
        assert validation.get("optionsSyncValid") == True
        assert validation.get("storageMatches") == True
        
        print(f"✓ Complete storage sync workflow passed for test port {test_port}")
        print(f"  - Storage sync: ✓")
        print(f"  - Popup sync: ✓") 
        print(f"  - Options sync: ✓")
        print(f"  - Validation: ✓")
    
    @pytest.mark.asyncio
    async def test_test_override_priority(self, server_with_extension):
        """Test that test overrides take priority over regular settings"""
        server, firefox, test_port = server_with_extension
        
        # Get storage values
        storage = await server.get_storage_values()
        
        # Get UI states
        popup_state = await server.get_popup_state() 
        options_state = await server.get_options_state()
        
        # Verify all returned successfully
        assert "error" not in storage
        assert "error" not in popup_state
        assert "error" not in options_state
        
        # Test overrides should take priority
        regular_port = storage.get("port", 8765)
        test_override_port = storage.get("testPort")
        
        # Verify test override exists and is different from regular port
        assert test_override_port is not None, "testPort override should exist"
        assert test_override_port == test_port, f"testPort should be {test_port}"
        
        # Verify UI displays test override, not regular port
        assert popup_state["effectivePort"] == test_override_port, "Popup should show test port"
        assert options_state["displayPort"] == test_override_port, "Options should show test port"
        
        # If regular port is different, verify it's NOT being used
        if regular_port != test_override_port:
            assert popup_state["effectivePort"] != regular_port, "Popup should not show regular port"
            assert options_state["displayPort"] != regular_port, "Options should not show regular port"
        
        print(f"✓ Test override priority working: {test_override_port} > {regular_port}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])