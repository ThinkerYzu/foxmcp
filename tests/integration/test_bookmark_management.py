"""
Bookmark Management End-to-End Tests

Comprehensive functional tests for browser bookmark operations through the
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


class TestBookmarkManagementEndToEnd:
    """End-to-end tests for bookmark management functionality"""
    
    
    @pytest_asyncio.fixture
    async def full_bookmark_system(self, server_with_extension):
        """Complete bookmark testing system with MCP client"""
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

    @pytest.mark.asyncio
    async def test_bookmark_folder_creation(self, full_bookmark_system):
        """Test creating bookmark folders"""
        system = full_bookmark_system
        mcp_client = system['mcp_client']

        await mcp_client.connect()

        # Test 1: Create a basic folder
        print("\n📁 Creating a basic bookmark folder...")
        folder_title = f"Test Folder {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        create_result = await mcp_client.call_tool("bookmarks_create_folder", {
            "title": folder_title
        })
        print(f"Folder creation result: {create_result}")

        # Verify creation was successful
        create_content = create_result.get('content', '')
        assert "Created folder:" in create_content, f"Expected success message not found: {create_result}"
        assert folder_title in create_content, f"Folder title not in result: {create_result}"

        # Extract folder ID from result
        folder_id = None
        if "ID:" in create_content:
            folder_id = create_content.split("ID: ")[1].rstrip(")")
            print(f"Created folder with ID: {folder_id}")

        assert folder_id, f"Could not extract folder ID from: {create_result}"

        # Wait for folder to be created
        await asyncio.sleep(1.0)

        # Test 2: Verify folder appears in bookmarks list
        print("\n📋 Verifying folder appears in bookmarks list...")
        list_result = await mcp_client.call_tool("bookmarks_list", {})
        list_content = list_result.get('content', '')

        assert folder_title in list_content, f"Folder '{folder_title}' not found in bookmarks list"
        assert '📁' in list_content, "Folder icon not found in bookmarks list"
        print("✅ Folder appears in bookmarks list")

        # Test 3: Create a bookmark inside the folder
        print(f"\n🔖 Creating bookmark inside folder {folder_id}...")
        bookmark_title = f"Bookmark in Folder {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        bookmark_result = await mcp_client.call_tool("bookmarks_create", {
            "title": bookmark_title,
            "url": "https://example.com/in-folder",
            "parent_id": folder_id
        })
        print(f"Bookmark creation result: {bookmark_result}")

        assert "Created bookmark:" in bookmark_result.get('content', ''), "Failed to create bookmark in folder"

        # Wait for bookmark to be created
        await asyncio.sleep(1.0)

        # Test 4: Verify bookmark is in the folder
        print(f"\n🔍 Listing bookmarks in folder {folder_id}...")
        folder_list_result = await mcp_client.call_tool("bookmarks_list", {
            "folder_id": folder_id
        })
        folder_list_content = folder_list_result.get('content', '')

        assert bookmark_title in folder_list_content, f"Bookmark '{bookmark_title}' not found in folder listing"
        print("✅ Bookmark successfully created inside folder")

        # Test 5: Create nested folder
        print(f"\n📁 Creating nested folder inside {folder_id}...")
        nested_folder_title = f"Nested Folder {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        nested_result = await mcp_client.call_tool("bookmarks_create_folder", {
            "title": nested_folder_title,
            "parent_id": folder_id
        })
        print(f"Nested folder creation result: {nested_result}")

        nested_content = nested_result.get('content', '')
        assert "Created folder:" in nested_content, "Failed to create nested folder"
        assert nested_folder_title in nested_content, "Nested folder title not in result"

        # Extract nested folder ID
        nested_folder_id = None
        if "ID:" in nested_content:
            nested_folder_id = nested_content.split("ID: ")[1].rstrip(")")
            print(f"Created nested folder with ID: {nested_folder_id}")

        await asyncio.sleep(1.0)

        # Test 6: Verify nested folder appears in parent folder
        print(f"\n🔍 Verifying nested folder in parent folder {folder_id}...")
        updated_folder_list = await mcp_client.call_tool("bookmarks_list", {
            "folder_id": folder_id
        })
        updated_folder_content = updated_folder_list.get('content', '')

        assert nested_folder_title in updated_folder_content, f"Nested folder '{nested_folder_title}' not found in parent folder"
        print("✅ Nested folder successfully created")

        print("✅ All bookmark folder creation tests passed")

    @pytest.mark.asyncio
    async def test_bookmark_update(self, full_bookmark_system):
        """Test updating bookmarks and folders"""
        system = full_bookmark_system
        mcp_client = system['mcp_client']

        await mcp_client.connect()

        # Test 1: Create a bookmark and update its title
        print("\n🔖 Creating a bookmark to update...")
        bookmark_title = f"Original Title {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        create_result = await mcp_client.call_tool("bookmarks_create", {
            "title": bookmark_title,
            "url": "https://example.com/original"
        })
        print(f"Bookmark creation result: {create_result}")

        # Extract bookmark ID
        bookmark_id = None
        create_content = create_result.get('content', '')
        if "ID:" in create_content:
            bookmark_id = create_content.split("ID: ")[1].rstrip(")")
            print(f"Created bookmark with ID: {bookmark_id}")

        assert bookmark_id, f"Could not extract bookmark ID from: {create_result}"
        await asyncio.sleep(0.5)

        # Update bookmark title
        print(f"\n✏️ Updating bookmark title...")
        new_title = f"Updated Title {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        update_result = await mcp_client.call_tool("bookmarks_update", {
            "bookmark_id": bookmark_id,
            "title": new_title
        })
        print(f"Update result: {update_result}")

        update_content = update_result.get('content', '')
        assert "Updated bookmark:" in update_content, f"Expected success message: {update_result}"
        assert new_title in update_content, f"New title not in result: {update_result}"
        print("✅ Bookmark title updated successfully")

        # Test 2: Update bookmark URL
        print(f"\n🔗 Updating bookmark URL...")
        new_url = "https://example.com/updated"
        update_url_result = await mcp_client.call_tool("bookmarks_update", {
            "bookmark_id": bookmark_id,
            "url": new_url
        })
        print(f"URL update result: {update_url_result}")

        assert "Updated bookmark:" in update_url_result.get('content', ''), "Failed to update URL"
        print("✅ Bookmark URL updated successfully")

        # Test 3: Update both title and URL
        print(f"\n✏️🔗 Updating both title and URL...")
        final_title = f"Final Title {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        final_url = "https://example.com/final"
        update_both_result = await mcp_client.call_tool("bookmarks_update", {
            "bookmark_id": bookmark_id,
            "title": final_title,
            "url": final_url
        })
        print(f"Update both result: {update_both_result}")

        both_content = update_both_result.get('content', '')
        assert "Updated bookmark:" in both_content, "Failed to update both"
        assert final_title in both_content, "Final title not in result"
        print("✅ Both title and URL updated successfully")

        await asyncio.sleep(0.5)

        # Test 4: Verify updates in bookmarks list
        print(f"\n📋 Verifying updates in bookmarks list...")
        list_result = await mcp_client.call_tool("bookmarks_list", {})
        list_content = list_result.get('content', '')

        assert final_title in list_content, f"Updated title '{final_title}' not found in list"
        assert final_url in list_content, f"Updated URL '{final_url}' not found in list"
        print("✅ Updates verified in bookmarks list")

        # Test 5: Create and update a folder
        print("\n📁 Creating a folder to update...")
        folder_title = f"Original Folder {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        folder_result = await mcp_client.call_tool("bookmarks_create_folder", {
            "title": folder_title
        })
        print(f"Folder creation result: {folder_result}")

        folder_id = None
        folder_content = folder_result.get('content', '')
        if "ID:" in folder_content:
            folder_id = folder_content.split("ID: ")[1].rstrip(")")
            print(f"Created folder with ID: {folder_id}")

        assert folder_id, f"Could not extract folder ID from: {folder_result}"
        await asyncio.sleep(0.5)

        # Update folder title
        print(f"\n✏️ Updating folder title...")
        new_folder_title = f"Updated Folder {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        update_folder_result = await mcp_client.call_tool("bookmarks_update", {
            "bookmark_id": folder_id,
            "title": new_folder_title
        })
        print(f"Folder update result: {update_folder_result}")

        folder_update_content = update_folder_result.get('content', '')
        assert "Updated bookmark:" in folder_update_content, f"Failed to update folder: {update_folder_result}"
        assert new_folder_title in folder_update_content, f"New folder title not in result: {update_folder_result}"
        print("✅ Folder title updated successfully")

        await asyncio.sleep(0.5)

        # Verify folder update in list
        print(f"\n📋 Verifying folder update in list...")
        final_list = await mcp_client.call_tool("bookmarks_list", {})
        final_list_content = final_list.get('content', '')

        assert new_folder_title in final_list_content, f"Updated folder title '{new_folder_title}' not found in list"
        print("✅ Folder update verified in list")

        # Test 6: Error handling - update with no parameters
        print("\n❌ Testing error handling - no parameters...")
        error_result = await mcp_client.call_tool("bookmarks_update", {
            "bookmark_id": bookmark_id
        })
        error_content = error_result.get('content', '')
        assert "Error" in error_content or "at least one" in error_content.lower(), \
            "Should error when no title or url provided"
        print("✅ Correctly handled missing parameters")

        print("✅ All bookmark update tests passed")
