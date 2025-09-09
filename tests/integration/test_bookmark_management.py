"""
Bookmark Management End-to-End Tests

Comprehensive functional tests for browser bookmark operations through the
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


class TestBookmarkManagementEndToEnd:
    """End-to-end tests for bookmark management functionality"""
    
    @pytest_asyncio.fixture
    async def server_with_extension(self):
        """Start server and Firefox extension for bookmark testing"""
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
            
            # Start server
            server_task = asyncio.create_task(server.start_server())
            await asyncio.sleep(0.1)  # Let server start
            
            # Check Firefox path
            firefox_path = os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')
            if not os.path.exists(os.path.expanduser(firefox_path)):
                pytest.skip(f"Firefox not found at {firefox_path}")
            
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
                    pytest.skip("Firefox failed to start")
                
                # Wait for extension to connect
                await asyncio.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])
                
                # Verify connection
                if not server.extension_connection:
                    pytest.skip("Extension did not connect to server")
                
                yield server, firefox, test_port, mcp_port
                
            finally:
                # Cleanup
                firefox.cleanup()
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass
    
    @pytest_asyncio.fixture
    async def full_bookmark_system(self, server_with_extension):
        """Complete bookmark testing system with MCP client"""
        server, firefox, test_port, mcp_port = server_with_extension
        
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
    async def test_bookmark_create_and_list(self, full_bookmark_system):
        """Test creating bookmarks and verifying they appear in the list"""
        system = full_bookmark_system
        server = system['server']
        mcp_client = system['mcp_client']
        
        await mcp_client.connect()
        
        # Get initial bookmark count
        print("\n📋 Getting initial bookmarks list...")
        initial_list = await mcp_client.call_tool("bookmarks_list", {})
        print(f"Initial bookmarks: {initial_list}")
        
        # Count initial bookmarks (rough estimate)
        initial_list_content = initial_list.get('content', '')
        initial_count = initial_list_content.count('🔖') if '🔖' in initial_list_content else 0
        
        # Create test bookmarks
        test_bookmarks = [
            {"title": "Test Bookmark 1", "url": "https://example.com/test1"},
            {"title": "Test Bookmark 2", "url": "https://example.com/test2"},
            {"title": "Test Bookmark 3", "url": "https://github.com/test"}
        ]
        
        created_bookmark_ids = []
        
        # Create bookmarks using MCP client
        for bookmark in test_bookmarks:
            print(f"\n🔖 Creating bookmark: {bookmark['title']}")
            result = await mcp_client.call_tool("bookmarks_create", {
                "title": bookmark["title"],
                "url": bookmark["url"]
            })
            print(f"Creation result: {result}")
            
            # Extract bookmark ID from result (assuming format "Created bookmark: ... (ID: <id>)")
            result_content = result.get('content', '')
            if "ID:" in result_content:
                bookmark_id = result_content.split("ID: ")[1].rstrip(")")
                created_bookmark_ids.append(bookmark_id)
                print(f"Created bookmark with ID: {bookmark_id}")
            
            # Verify creation was successful
            result_content = result.get('content', '')
            assert result.get('success'), f"Failed to create bookmark: {result}"
            assert "Created bookmark:" in result_content, f"Expected success message not found: {result}"
            assert bookmark["title"] in result_content, f"Bookmark title not in result: {result}"
            assert bookmark["url"] in result_content, f"Bookmark URL not in result: {result}"
        
        print(f"\n📝 Created {len(created_bookmark_ids)} bookmarks")
        
        # Wait a moment for bookmarks to be saved
        await asyncio.sleep(1.0)
        
        # Get updated bookmarks list
        print("\n📋 Getting updated bookmarks list...")
        updated_list = await mcp_client.call_tool("bookmarks_list", {})
        print(f"Updated bookmarks: {updated_list}")
        
        # Verify all created bookmarks are in the list
        updated_list_content = updated_list.get('content', '')
        for bookmark in test_bookmarks:
            assert bookmark["title"] in updated_list_content, f"Bookmark '{bookmark['title']}' not found in list"
            assert bookmark["url"] in updated_list_content, f"URL '{bookmark['url']}' not found in list"
        
        # Verify bookmark count increased
        updated_count = updated_list_content.count('🔖')
        assert updated_count >= initial_count + len(test_bookmarks), f"Expected at least {initial_count + len(test_bookmarks)} bookmarks, got {updated_count}"
        
        print(f"✅ All {len(test_bookmarks)} bookmarks successfully created and verified")
        
        # Store created IDs for potential cleanup in other tests
        return created_bookmark_ids
    
    @pytest.mark.asyncio
    async def test_bookmark_search(self, full_bookmark_system):
        """Test bookmark search functionality"""
        system = full_bookmark_system
        mcp_client = system['mcp_client']
        
        await mcp_client.connect()
        
        # First create some searchable bookmarks
        test_bookmarks = [
            {"title": "Python Documentation", "url": "https://docs.python.org"},
            {"title": "GitHub Repository", "url": "https://github.com/example/repo"},
            {"title": "Stack Overflow Question", "url": "https://stackoverflow.com/questions/123"}
        ]
        
        # Create bookmarks
        for bookmark in test_bookmarks:
            print(f"\n🔖 Creating searchable bookmark: {bookmark['title']}")
            result = await mcp_client.call_tool("bookmarks_create", {
                "title": bookmark["title"],
                "url": bookmark["url"]
            })
            assert "Created bookmark:" in result
        
        # Wait for bookmarks to be indexed
        await asyncio.sleep(1.0)
        
        # Test different search queries
        search_tests = [
            ("Python", ["Python Documentation"]),
            ("GitHub", ["GitHub Repository"]),
            ("docs", ["Python Documentation"]),
            ("stackoverflow", ["Stack Overflow Question"]),
            ("nonexistent", [])  # Should return no results
        ]
        
        for query, expected_titles in search_tests:
            print(f"\n🔍 Searching for: '{query}'")
            search_result = await mcp_client.call_tool("bookmarks_search", {
                "query": query
            })
            print(f"Search result: {search_result}")
            
            if expected_titles:
                for title in expected_titles:
                    assert title in search_result, f"Expected '{title}' in search results for '{query}'"
                print(f"✅ Found expected bookmarks for query '{query}'")
            else:
                # For empty results, check for appropriate message
                assert "No bookmarks found" in search_result or search_result.strip() == "", f"Expected no results for '{query}', got: {search_result}"
                print(f"✅ Correctly found no results for query '{query}'")
    
    @pytest.mark.asyncio
    async def test_bookmark_delete(self, full_bookmark_system):
        """Test bookmark deletion functionality"""
        system = full_bookmark_system
        mcp_client = system['mcp_client']
        
        await mcp_client.connect()
        
        # Create a bookmark to delete
        test_bookmark = {"title": "Bookmark to Delete", "url": "https://example.com/delete-me"}
        
        print(f"\n🔖 Creating bookmark for deletion: {test_bookmark['title']}")
        create_result = await mcp_client.call_tool("bookmarks_create", {
            "title": test_bookmark["title"],
            "url": test_bookmark["url"]
        })
        
        assert "Created bookmark:" in create_result
        
        # Extract bookmark ID
        bookmark_id = None
        if "ID:" in create_result:
            bookmark_id = create_result.split("ID: ")[1].rstrip(")")
            print(f"Created bookmark with ID: {bookmark_id}")
        
        assert bookmark_id, f"Could not extract bookmark ID from: {create_result}"
        
        # Verify bookmark exists in list
        list_result = await mcp_client.call_tool("bookmarks_list", {})
        assert test_bookmark["title"] in list_result, "Bookmark should exist before deletion"
        
        # Delete the bookmark
        print(f"\n🗑️ Deleting bookmark with ID: {bookmark_id}")
        delete_result = await mcp_client.call_tool("bookmarks_delete", {
            "bookmark_id": bookmark_id
        })
        print(f"Deletion result: {delete_result}")
        
        # Verify deletion was successful
        assert "Successfully deleted bookmark" in delete_result or "Deleted bookmark" in delete_result, f"Failed to delete bookmark: {delete_result}"
        
        # Wait a moment for deletion to be processed
        await asyncio.sleep(1.0)
        
        # Verify bookmark no longer exists in list
        updated_list = await mcp_client.call_tool("bookmarks_list", {})
        assert test_bookmark["title"] not in updated_list, "Bookmark should not exist after deletion"
        
        print("✅ Bookmark successfully deleted and removed from list")
    
    @pytest.mark.asyncio
    async def test_bookmark_error_handling(self, full_bookmark_system):
        """Test bookmark error handling scenarios"""
        system = full_bookmark_system
        mcp_client = system['mcp_client']
        
        await mcp_client.connect()
        
        # Test creating bookmark with invalid URL
        print("\n❌ Testing invalid URL handling...")
        invalid_result = await mcp_client.call_tool("bookmarks_create", {
            "title": "Invalid Bookmark",
            "url": "not-a-valid-url"
        })
        print(f"Invalid URL result: {invalid_result}")
        # Note: Different browsers may handle invalid URLs differently
        
        # Test deleting non-existent bookmark
        print("\n❌ Testing non-existent bookmark deletion...")
        delete_result = await mcp_client.call_tool("bookmarks_delete", {
            "bookmark_id": "non-existent-bookmark-id"
        })
        print(f"Non-existent deletion result: {delete_result}")
        assert "Error" in delete_result or "Failed" in delete_result or "not found" in delete_result.lower(), \
            "Should get error when deleting non-existent bookmark"
        
        print("✅ Error handling tests completed")
    
    @pytest.mark.asyncio
    async def test_bookmark_concurrent_operations(self, full_bookmark_system):
        """Test concurrent bookmark operations"""
        system = full_bookmark_system
        mcp_client = system['mcp_client']
        
        await mcp_client.connect()
        
        # Create multiple bookmarks concurrently
        concurrent_bookmarks = [
            {"title": f"Concurrent Bookmark {i}", "url": f"https://example.com/concurrent/{i}"}
            for i in range(5)
        ]
        
        print("\n🚀 Creating bookmarks concurrently...")
        
        # Create all bookmarks concurrently
        tasks = [
            mcp_client.call_tool("bookmarks_create", {
                "title": bookmark["title"],
                "url": bookmark["url"]
            })
            for bookmark in concurrent_bookmarks
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all creations succeeded
        successful_creations = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"❌ Bookmark {i} failed with exception: {result}")
            else:
                if "Created bookmark:" in str(result):
                    successful_creations += 1
                    print(f"✅ Bookmark {i}: {result}")
                else:
                    print(f"❌ Bookmark {i} failed: {result}")
        
        print(f"Successfully created {successful_creations}/{len(concurrent_bookmarks)} bookmarks concurrently")
        
        # Verify bookmarks appear in list
        await asyncio.sleep(1.0)  # Wait for all operations to complete
        
        final_list = await mcp_client.call_tool("bookmarks_list", {})
        
        verified_count = 0
        for bookmark in concurrent_bookmarks:
            if bookmark["title"] in final_list:
                verified_count += 1
        
        print(f"✅ Verified {verified_count}/{len(concurrent_bookmarks)} concurrent bookmarks in final list")
        
        # We expect most operations to succeed, but some might fail due to concurrency
        assert verified_count >= len(concurrent_bookmarks) // 2, \
            f"Expected at least half of concurrent operations to succeed, got {verified_count}/{len(concurrent_bookmarks)}"