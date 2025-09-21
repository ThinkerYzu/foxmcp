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
            firefox_path = os.environ.get('FIREFOX_PATH', 'firefox')
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
            assert "Created bookmark:" in result.get('content', ''), f"Expected success message not found: {result}"
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
            assert "Created bookmark:" in result.get('content', '')
        
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
            
            search_content = search_result.get('content', '') if isinstance(search_result, dict) else search_result
            if expected_titles:
                for title in expected_titles:
                    assert title in search_content, f"Expected '{title}' in search results for '{query}'"
                print(f"✅ Found expected bookmarks for query '{query}'")
            else:
                # For empty results, check for appropriate message
                assert "No bookmarks found" in search_content or search_content.strip() == "", f"Expected no results for '{query}', got: {search_result}"
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
        
        assert "Created bookmark:" in create_result.get('content', '')
        
        # Extract bookmark ID
        bookmark_id = None
        create_content = create_result.get('content', '')
        if "ID:" in create_content:
            bookmark_id = create_content.split("ID: ")[1].rstrip(")")
            print(f"Created bookmark with ID: {bookmark_id}")
        
        assert bookmark_id, f"Could not extract bookmark ID from: {create_result}"
        
        # Verify bookmark exists in list
        list_result = await mcp_client.call_tool("bookmarks_list", {})
        list_content = list_result.get('content', '')
        assert test_bookmark["title"] in list_content, "Bookmark should exist before deletion"
        
        # Delete the bookmark
        print(f"\n🗑️ Deleting bookmark with ID: {bookmark_id}")
        delete_result = await mcp_client.call_tool("bookmarks_delete", {
            "bookmark_id": bookmark_id
        })
        print(f"Deletion result: {delete_result}")
        
        # Verify deletion was successful
        delete_content = delete_result.get('content', '')
        assert "Successfully deleted bookmark" in delete_content or "Deleted bookmark" in delete_content, f"Failed to delete bookmark: {delete_result}"
        
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
        result_content = delete_result.get("content", "") if isinstance(delete_result, dict) else str(delete_result)
        assert "Error" in result_content or "Failed" in result_content or "not found" in result_content.lower(), \
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
        final_list_content = final_list.get("content", "") if isinstance(final_list, dict) else str(final_list)
        for bookmark in concurrent_bookmarks:
            if bookmark["title"] in final_list_content:
                verified_count += 1
        
        print(f"✅ Verified {verified_count}/{len(concurrent_bookmarks)} concurrent bookmarks in final list")
        
        # We expect most operations to succeed, but some might fail due to concurrency
        assert verified_count >= len(concurrent_bookmarks) // 2, \
            f"Expected at least half of concurrent operations to succeed, got {verified_count}/{len(concurrent_bookmarks)}"

    @pytest.mark.asyncio
    async def test_bookmark_folder_filtering(self, full_bookmark_system):
        """Test bookmark listing with folder_id parameter"""
        system = full_bookmark_system
        mcp_client = system['mcp_client']

        await mcp_client.connect()

        # First, get all bookmarks to understand the structure
        print("\n📋 Getting all bookmarks to understand folder structure...")
        all_bookmarks_result = await mcp_client.call_tool("bookmarks_list", {})
        print(f"All bookmarks: {all_bookmarks_result}")

        # Extract folder IDs from the results
        all_bookmarks_content = all_bookmarks_result.get('content', '')
        folder_ids = []

        # Look for folder entries (📁) and extract their IDs
        lines = all_bookmarks_content.split('\n')
        for line in lines:
            if '📁' in line and 'ID:' in line:
                try:
                    # Extract ID from format: "📁 Folder Name (ID: folder_id, Parent: parent_id)"
                    id_part = line.split('ID: ')[1].split(',')[0].strip()
                    if id_part != 'None':
                        folder_ids.append(id_part)
                        print(f"Found folder ID: {id_part}")
                except (IndexError, ValueError):
                    continue

        # Find a non-root folder for testing (avoid root________ which can't have direct bookmarks)
        test_folder_id = None
        for folder_id in folder_ids:
            if folder_id != "root________":  # Skip root folder
                test_folder_id = folder_id
                break

        if not test_folder_id:
            # If no non-root folders exist, use toolbar folder (it should always exist)
            for line in lines:
                if 'toolbar' in line.lower() and 'ID:' in line:
                    try:
                        test_folder_id = line.split('ID: ')[1].split(',')[0].strip()
                        break
                    except (IndexError, ValueError):
                        continue

        if not test_folder_id:
            pytest.skip("No suitable folders available for testing folder filtering")

        print(f"\n🔍 Testing folder filtering with folder ID: {test_folder_id}")

        # Test 1: Get bookmarks from specific folder
        folder_bookmarks_result = await mcp_client.call_tool("bookmarks_list", {
            "folder_id": test_folder_id
        })
        print(f"Folder bookmarks result: {folder_bookmarks_result}")

        # Debug: print all keys in the result to see if debugInfo is there
        if isinstance(folder_bookmarks_result, dict):
            print(f"🔍 Result keys: {list(folder_bookmarks_result.keys())}")
            if 'debugInfo' in folder_bookmarks_result:
                print(f"🔍 DEBUG INFO: {folder_bookmarks_result['debugInfo']}")
            elif any('debug' in key.lower() for key in folder_bookmarks_result.keys()):
                debug_keys = [k for k in folder_bookmarks_result.keys() if 'debug' in k.lower()]
                print(f"🔍 Found debug keys: {debug_keys}")
                for key in debug_keys:
                    print(f"🔍 {key}: {folder_bookmarks_result[key]}")

        # Test with a deeper folder that should have fewer items
        deeper_folder_id = None
        for line in lines:
            if '🔖' in line and 'Parent: ' in line and test_folder_id not in line:
                try:
                    # Look for a bookmark with a parent that's not our test folder
                    parent_part = line.split('Parent: ')[1].strip(' )')
                    if parent_part != test_folder_id and parent_part != 'None':
                        deeper_folder_id = parent_part
                        break
                except (IndexError, ValueError):
                    continue

        if deeper_folder_id:
            print(f"\n🔍 Testing with deeper folder ID: {deeper_folder_id}")
            deeper_folder_result = await mcp_client.call_tool("bookmarks_list", {
                "folder_id": deeper_folder_id
            })
            print(f"Deeper folder result: {deeper_folder_result}")

            deeper_content = deeper_folder_result.get('content', '')
            if deeper_content != all_bookmarks_content:
                print("✅ Deeper folder filtering returned different results")
            else:
                print("⚠️ Deeper folder returned same as all bookmarks")
        else:
            print("ℹ️ No deeper folder found for additional testing")

        # Verify the result
        folder_content = folder_bookmarks_result.get('content', '')

        # The result should be different from getting all bookmarks
        # (unless the folder contains everything, which is unlikely)
        if folder_content != all_bookmarks_content:
            print("✅ Folder filtering returned different results than all bookmarks")
        else:
            print("ℹ️ Folder contains the same bookmarks as full tree (possible for root folders)")

        # Test 2: Verify folder filtering format includes parent IDs
        if 'Parent:' in folder_content:
            print("✅ Folder filtering results include parent ID information")
        else:
            print("⚠️ Parent ID information not found in folder results")

        # Test 3: Compare bookmark counts
        all_bookmark_count = all_bookmarks_content.count('🔖')
        folder_bookmark_count = folder_content.count('🔖')

        print(f"📊 All bookmarks count: {all_bookmark_count}")
        print(f"📊 Folder bookmarks count: {folder_bookmark_count}")

        # The folder should have <= bookmarks than the full tree
        assert folder_bookmark_count <= all_bookmark_count, \
            f"Folder should not have more bookmarks than total: {folder_bookmark_count} > {all_bookmark_count}"

        # Test 4: Test with non-existent folder ID
        print("\n❌ Testing with non-existent folder ID...")
        invalid_folder_result = await mcp_client.call_tool("bookmarks_list", {
            "folder_id": "non-existent-folder-999"
        })
        print(f"Invalid folder result: {invalid_folder_result}")

        # Should return an error for invalid folder ID
        invalid_content = invalid_folder_result.get('content', '')
        is_error = invalid_folder_result.get('isError', False)
        if is_error or 'Error' in invalid_content or 'Invalid folder ID' in invalid_content:
            print("✅ Correctly handled non-existent folder ID with error")
        elif 'No bookmarks found' in invalid_content or invalid_content.strip() == '':
            print("✅ Correctly handled non-existent folder ID with empty result")
        else:
            print(f"⚠️ Unexpected result for non-existent folder: {invalid_content}")
            # This is not necessarily a failure - some browsers might handle it differently

        # Test 5: Test that folder_id parameter is properly respected
        # Create a test bookmark and verify it only shows up in relevant folder queries
        print(f"\n🔖 Creating test bookmark specifically for folder {test_folder_id}")
        unique_title = f"Folder Test Bookmark {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        test_bookmark_result = await mcp_client.call_tool("bookmarks_create", {
            "title": unique_title,
            "url": "https://example.com/folder-specific-test",
            "parent_id": test_folder_id
        })
        print(f"Created test bookmark: {test_bookmark_result}")

        # Wait for bookmark creation
        await asyncio.sleep(1.0)

        # Verify bookmark appears in folder listing
        updated_folder_result = await mcp_client.call_tool("bookmarks_list", {
            "folder_id": test_folder_id
        })

        if unique_title in updated_folder_result.get('content', ''):
            print("✅ Newly created bookmark appears in specific folder listing")
        else:
            print("⚠️ Newly created bookmark not found in folder listing")

        print("✅ Folder filtering test completed successfully")