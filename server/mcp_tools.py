#!/usr/bin/env python3
"""
MCP Tool definitions for FoxMCP server
These tools bridge browser functions through WebSocket to the Firefox extension
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastmcp import FastMCP
from pydantic import BaseModel, Field

class FoxMCPTools:
    """MCP tools that communicate with Firefox extension via WebSocket"""
    
    def __init__(self, websocket_server):
        """Initialize with reference to WebSocket server"""
        self.websocket_server = websocket_server
        self.mcp = FastMCP("FoxMCP")
        self._setup_tools()
    
    def _setup_tools(self):
        """Set up all MCP tool definitions"""
        self._setup_tab_tools()
        self._setup_history_tools()
        self._setup_bookmark_tools()
        self._setup_navigation_tools()
        self._setup_content_tools()
    
    def _setup_tab_tools(self):
        """Setup tab management tools"""
        
        # Tab List Tool
        @self.mcp.tool()
        async def tabs_list() -> str:
            """List all open browser tabs"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.list",
                "data": {},
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error getting tabs: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                tabs = response["data"].get("tabs", [])
                if not tabs:
                    # More informative message for debugging
                    return f"No tabs found. Extension response: {response.get('data', {})}"
                
                result = f"Open tabs ({len(tabs)} found):\n"
                for tab in tabs:
                    active = " (active)" if tab.get("active") else ""
                    result += f"- ID {tab.get('id')}: {tab.get('title', 'No title')} - {tab.get('url', 'No URL')}{active}\n"
                return result
            
            return "Unable to retrieve tabs"
        
        # Tab Create Tool
        @self.mcp.tool()
        async def tabs_create(
            url: str,
            active: bool = True,
            pinned: bool = False,
            window_id: Optional[int] = None
        ) -> str:
            """Create a new browser tab
            
            Args:
                url: URL to open in the new tab
                active: Whether the tab should be active (default: True)
                pinned: Whether the tab should be pinned (default: False)
                window_id: Window ID to create tab in (optional)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request", 
                "action": "tabs.create",
                "data": {
                    "url": url,
                    "active": active,
                    "pinned": pinned,
                    **({"windowId": window_id} if window_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error creating tab: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                tab = response["data"].get("tab", {})
                return f"Created tab: ID {tab.get('id')} - {tab.get('title', 'Loading...')} - {tab.get('url', url)}"
            
            return "Unable to create tab"
        
        # Tab Close Tool
        @self.mcp.tool()
        async def tabs_close(tab_id: int) -> str:
            """Close a browser tab
            
            Args:
                tab_id: ID of the tab to close
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.close", 
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error closing tab: {response['error']}"
            
            if response.get("type") == "response":
                return f"Successfully closed tab {tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to close tab: {error_msg}"
            
            return f"Unable to close tab {tab_id}"
        
        # Tab Switch Tool
        @self.mcp.tool()
        async def tabs_switch(tab_id: int) -> str:
            """Switch to a specific browser tab
            
            Args:
                tab_id: ID of the tab to switch to
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.switch",
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error switching to tab: {response['error']}"
            
            if response.get("type") == "response":
                return f"Successfully switched to tab {tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error") 
                return f"Failed to switch to tab: {error_msg}"
            
            return f"Unable to switch to tab {tab_id}"
    
    def _setup_history_tools(self):
        """Setup history management tools"""
        
        # History Query Tool
        @self.mcp.tool()
        async def history_query(
            query: str,
            max_results: int = 50,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None
        ) -> str:
            """Search browser history
            
            Args:
                query: Search query for history
                max_results: Maximum number of results (default: 50)
                start_time: Start time filter (ISO format, optional)
                end_time: End time filter (ISO format, optional)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.query",
                "data": {
                    "query": query,
                    "maxResults": max_results,
                    **({"startTime": start_time} if start_time else {}),
                    **({"endTime": end_time} if end_time else {})
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error querying history: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                items = response["data"].get("items", [])
                total_count = response["data"].get("totalCount", len(items))
                
                if not items:
                    return f"No history items found for query: {query}"
                
                result = f"Found {total_count} history items for '{query}':\n"
                for item in items:
                    visit_time = item.get("visitTime", "Unknown time")
                    visit_count = item.get("visitCount", 0)
                    result += f"- {item.get('title', 'No title')} - {item.get('url', 'No URL')} (visited {visit_count} times, last: {visit_time})\n"
                
                return result
            
            return f"Unable to query history for: {query}"
        
        # WebSocket Connection Status Tool (for debugging)
        @self.mcp.tool()
        async def debug_websocket_status() -> str:
            """Debug WebSocket connection status
            
            Returns information about the browser extension connection
            """
            if not hasattr(self.websocket_server, 'connected_clients'):
                return "WebSocket server doesn't track connected clients"
            
            try:
                client_count = len(getattr(self.websocket_server, 'connected_clients', []))
                return f"WebSocket status: {client_count} browser extension(s) connected"
            except Exception as e:
                return f"WebSocket status check failed: {e}"

        # Get Recent History Tool
        @self.mcp.tool()
        async def history_get_recent(count: int = 10) -> str:
            """Get recent browser history
            
            Args:
                count: Number of recent items to get (default: 10)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.recent",
                "data": {
                    "count": count
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            # Debug logging for troubleshooting
            import json
            print(f"🔍 DEBUG - Recent history WebSocket response: {json.dumps(response, indent=2)}")
            
            if "error" in response:
                return f"Error getting recent history: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                items = response["data"].get("items", [])
                
                if not items:
                    return "No recent history items found"
                
                result = f"Recent {len(items)} history items:\n"
                for item in items:
                    visit_time = item.get("visitTime", "Unknown time")
                    result += f"- {item.get('title', 'No title')} - {item.get('url', 'No URL')} (last visit: {visit_time})\n"
                
                return result
            
            # More detailed error message for debugging
            return f"Unable to get recent history. Response type: {response.get('type')}, has_data: {'data' in response}, keys: {list(response.keys())}"
        
        # Delete History Item Tool  
        @self.mcp.tool()
        async def history_delete_item(url: str) -> str:
            """Delete a specific history item
            
            Args:
                url: URL of the history item to delete
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request", 
                "action": "history.delete_item",
                "data": {
                    "url": url
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error deleting history item: {response['error']}"
            
            if response.get("type") == "response":
                return f"Successfully deleted history item: {params.url}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to delete history item: {error_msg}"
            
            return f"Unable to delete history item: {params.url}"
    
    def _setup_bookmark_tools(self):
        """Setup bookmark management tools"""
        
        # List Bookmarks Tool
        class BookmarkListParams(BaseModel):
            """Parameters for listing bookmarks"""
            folder_id: Optional[str] = Field(default=None, description="Folder ID to list bookmarks from")
        
        @self.mcp.tool()
        async def bookmarks_list(params: BookmarkListParams) -> str:
            """List browser bookmarks"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.list",
                "data": {
                    **({"folderId": params.folder_id} if params.folder_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error listing bookmarks: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                bookmarks = response["data"].get("bookmarks", [])
                
                if not bookmarks:
                    return "No bookmarks found"
                
                result = "Bookmarks:\n"
                for bookmark in bookmarks:
                    if bookmark.get("isFolder", False):
                        result += f"📁 {bookmark.get('title', 'Untitled Folder')} (ID: {bookmark.get('id')})\n"
                    else:
                        result += f"🔖 {bookmark.get('title', 'Untitled')} - {bookmark.get('url', 'No URL')} (ID: {bookmark.get('id')})\n"
                
                return result
            
            return "Unable to list bookmarks"
        
        # Search Bookmarks Tool
        class BookmarkSearchParams(BaseModel):
            """Parameters for searching bookmarks"""
            query: str = Field(description="Search query for bookmarks")
        
        @self.mcp.tool()
        async def bookmarks_search(params: BookmarkSearchParams) -> str:
            """Search browser bookmarks"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.search",
                "data": {
                    "query": params.query
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error searching bookmarks: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                bookmarks = response["data"].get("bookmarks", [])
                
                if not bookmarks:
                    return f"No bookmarks found for query: {params.query}"
                
                result = f"Found {len(bookmarks)} bookmarks for '{params.query}':\n"
                for bookmark in bookmarks:
                    if not bookmark.get("isFolder", False):
                        result += f"🔖 {bookmark.get('title', 'Untitled')} - {bookmark.get('url', 'No URL')}\n"
                
                return result
            
            return f"Unable to search bookmarks for: {params.query}"
        
        # Create Bookmark Tool
        class BookmarkCreateParams(BaseModel):
            """Parameters for creating a bookmark"""
            title: str = Field(description="Title of the bookmark")
            url: str = Field(description="URL of the bookmark")
            parent_id: Optional[str] = Field(default=None, description="Parent folder ID")
        
        @self.mcp.tool()
        async def bookmarks_create(params: BookmarkCreateParams) -> str:
            """Create a new bookmark"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.create",
                "data": {
                    "title": params.title,
                    "url": params.url,
                    **({"parentId": params.parent_id} if params.parent_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error creating bookmark: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                bookmark = response["data"].get("bookmark", {})
                return f"Created bookmark: {bookmark.get('title', params.title)} - {bookmark.get('url', params.url)} (ID: {bookmark.get('id')})"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to create bookmark: {error_msg}"
            
            return f"Unable to create bookmark: {params.title}"
        
        # Delete Bookmark Tool
        class BookmarkDeleteParams(BaseModel):
            """Parameters for deleting a bookmark"""
            bookmark_id: str = Field(description="ID of the bookmark to delete")
        
        @self.mcp.tool()
        async def bookmarks_delete(params: BookmarkDeleteParams) -> str:
            """Delete a bookmark"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.delete",
                "data": {
                    "bookmarkId": params.bookmark_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error deleting bookmark: {response['error']}"
            
            if response.get("type") == "response":
                return f"Successfully deleted bookmark {params.bookmark_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to delete bookmark: {error_msg}"
            
            return f"Unable to delete bookmark {params.bookmark_id}"
    
    def _setup_navigation_tools(self):
        """Setup navigation tools"""
        
        # Navigate Back Tool
        class NavigationBackParams(BaseModel):
            """Parameters for navigating back"""
            tab_id: int = Field(description="ID of the tab to navigate back in")
        
        @self.mcp.tool()
        async def navigation_back(params: NavigationBackParams) -> str:
            """Navigate back in browser history for a tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.back",
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error navigating back: {response['error']}"
            
            if response.get("type") == "response":
                return f"Successfully navigated back in tab {params.tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to navigate back: {error_msg}"
            
            return f"Unable to navigate back in tab {params.tab_id}"
        
        # Navigate Forward Tool
        class NavigationForwardParams(BaseModel):
            """Parameters for navigating forward"""
            tab_id: int = Field(description="ID of the tab to navigate forward in")
        
        @self.mcp.tool()
        async def navigation_forward(params: NavigationForwardParams) -> str:
            """Navigate forward in browser history for a tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.forward",
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error navigating forward: {response['error']}"
            
            if response.get("type") == "response":
                return f"Successfully navigated forward in tab {params.tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to navigate forward: {error_msg}"
            
            return f"Unable to navigate forward in tab {params.tab_id}"
        
        # Reload Page Tool
        class NavigationReloadParams(BaseModel):
            """Parameters for reloading a page"""
            tab_id: int = Field(description="ID of the tab to reload")
            bypass_cache: bool = Field(default=False, description="Whether to bypass cache when reloading")
        
        @self.mcp.tool()
        async def navigation_reload(params: NavigationReloadParams) -> str:
            """Reload a page in a tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.reload",
                "data": {
                    "tabId": params.tab_id,
                    "bypassCache": params.bypass_cache
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error reloading page: {response['error']}"
            
            if response.get("type") == "response":
                cache_text = " (bypassing cache)" if params.bypass_cache else ""
                return f"Successfully reloaded tab {params.tab_id}{cache_text}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to reload page: {error_msg}"
            
            return f"Unable to reload tab {params.tab_id}"
        
        # Go to URL Tool
        class NavigationGoToUrlParams(BaseModel):
            """Parameters for navigating to a URL"""
            tab_id: int = Field(description="ID of the tab to navigate")
            url: str = Field(description="URL to navigate to")
        
        @self.mcp.tool()
        async def navigation_go_to_url(params: NavigationGoToUrlParams) -> str:
            """Navigate to a specific URL in a tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.go_to_url",
                "data": {
                    "tabId": params.tab_id,
                    "url": params.url
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error navigating to URL: {response['error']}"
            
            if response.get("type") == "response":
                return f"Successfully navigated tab {params.tab_id} to {params.url}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to navigate to URL: {error_msg}"
            
            return f"Unable to navigate tab {params.tab_id} to {params.url}"
    
    def _setup_content_tools(self):
        """Setup content access tools"""
        
        # Get Page Text Tool
        class ContentGetTextParams(BaseModel):
            """Parameters for getting page text content"""
            tab_id: int = Field(description="ID of the tab to get content from")
        
        @self.mcp.tool()
        async def content_get_text(params: ContentGetTextParams) -> str:
            """Get text content from a tab's page"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "content.get_text",
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error getting page text: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                text = response["data"].get("text", "")
                url = response["data"].get("url", "Unknown URL")
                title = response["data"].get("title", "Unknown Title")
                
                if not text:
                    return f"No text content found in tab {params.tab_id} ({title})"
                
                return f"Text content from {title} ({url}):\n\n{text[:2000]}{'...' if len(text) > 2000 else ''}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to get page text: {error_msg}"
            
            return f"Unable to get text content from tab {params.tab_id}"
        
        # Get Page HTML Tool
        class ContentGetHtmlParams(BaseModel):
            """Parameters for getting page HTML content"""
            tab_id: int = Field(description="ID of the tab to get HTML content from")
        
        @self.mcp.tool()
        async def content_get_html(params: ContentGetHtmlParams) -> str:
            """Get HTML content from a tab's page"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "content.get_html",
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error getting page HTML: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                html = response["data"].get("html", "")
                url = response["data"].get("url", "Unknown URL")
                title = response["data"].get("title", "Unknown Title")
                
                if not html:
                    return f"No HTML content found in tab {params.tab_id} ({title})"
                
                return f"HTML content from {title} ({url}):\n\n{html[:2000]}{'...' if len(html) > 2000 else ''}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to get page HTML: {error_msg}"
            
            return f"Unable to get HTML content from tab {params.tab_id}"
        
        # Execute Script Tool
        class ContentExecuteScriptParams(BaseModel):
            """Parameters for executing JavaScript in a tab"""
            tab_id: int = Field(description="ID of the tab to execute script in")
            code: str = Field(description="JavaScript code to execute")
        
        @self.mcp.tool()
        async def content_execute_script(params: ContentExecuteScriptParams) -> str:
            """Execute JavaScript code in a tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "content.execute_script",
                "data": {
                    "tabId": params.tab_id,
                    "code": params.code
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error executing script: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                result = response["data"].get("result")
                url = response["data"].get("url", "Unknown URL")
                
                if result is None:
                    return f"Script executed successfully in tab {params.tab_id} ({url}) - no return value"
                
                return f"Script result from tab {params.tab_id} ({url}):\n{result}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to execute script: {error_msg}"
            
            return f"Unable to execute script in tab {params.tab_id}"
    
    def get_mcp_app(self):
        """Get the FastMCP application instance"""
        return self.mcp