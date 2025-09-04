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
        class TabListParams(BaseModel):
            """Parameters for listing tabs"""
            pass
        
        @self.mcp.tool()
        async def tabs_list(params: TabListParams) -> str:
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
                    return "No tabs found"
                
                result = "Open tabs:\n"
                for tab in tabs:
                    active = " (active)" if tab.get("active") else ""
                    result += f"- ID {tab.get('id')}: {tab.get('title', 'No title')} - {tab.get('url', 'No URL')}{active}\n"
                return result
            
            return "Unable to retrieve tabs"
        
        # Tab Create Tool
        class TabCreateParams(BaseModel):
            """Parameters for creating a new tab"""
            url: str = Field(description="URL to open in the new tab")
            active: bool = Field(default=True, description="Whether the tab should be active")
            pinned: bool = Field(default=False, description="Whether the tab should be pinned")
            window_id: Optional[int] = Field(default=None, description="Window ID to create tab in")
        
        @self.mcp.tool()
        async def tabs_create(params: TabCreateParams) -> str:
            """Create a new browser tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request", 
                "action": "tabs.create",
                "data": {
                    "url": params.url,
                    "active": params.active,
                    "pinned": params.pinned,
                    **({"windowId": params.window_id} if params.window_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error creating tab: {response['error']}"
            
            if response.get("type") == "response" and "data" in response:
                tab = response["data"].get("tab", {})
                return f"Created tab: ID {tab.get('id')} - {tab.get('title', 'Loading...')} - {tab.get('url', params.url)}"
            
            return "Unable to create tab"
        
        # Tab Close Tool
        class TabCloseParams(BaseModel):
            """Parameters for closing a tab"""
            tab_id: int = Field(description="ID of the tab to close")
        
        @self.mcp.tool()
        async def tabs_close(params: TabCloseParams) -> str:
            """Close a browser tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.close", 
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error closing tab: {response['error']}"
            
            if response.get("type") == "response":
                return f"Successfully closed tab {params.tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to close tab: {error_msg}"
            
            return f"Unable to close tab {params.tab_id}"
        
        # Tab Switch Tool
        class TabSwitchParams(BaseModel):
            """Parameters for switching to a tab"""
            tab_id: int = Field(description="ID of the tab to switch to")
        
        @self.mcp.tool()
        async def tabs_switch(params: TabSwitchParams) -> str:
            """Switch to a specific browser tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.switch",
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
            if "error" in response:
                return f"Error switching to tab: {response['error']}"
            
            if response.get("type") == "response":
                return f"Successfully switched to tab {params.tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error") 
                return f"Failed to switch to tab: {error_msg}"
            
            return f"Unable to switch to tab {params.tab_id}"
    
    def _setup_history_tools(self):
        """Setup history management tools"""
        
        # History Query Tool
        class HistoryQueryParams(BaseModel):
            """Parameters for querying browser history"""
            query: str = Field(description="Search query for history")
            max_results: int = Field(default=50, description="Maximum number of results")
            start_time: Optional[str] = Field(default=None, description="Start time filter (ISO format)")
            end_time: Optional[str] = Field(default=None, description="End time filter (ISO format)")
        
        @self.mcp.tool()
        async def history_query(params: HistoryQueryParams) -> str:
            """Search browser history"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.query",
                "data": {
                    "query": params.query,
                    "maxResults": params.max_results,
                    **({"startTime": params.start_time} if params.start_time else {}),
                    **({"endTime": params.end_time} if params.end_time else {})
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
                    return f"No history items found for query: {params.query}"
                
                result = f"Found {total_count} history items for '{params.query}':\n"
                for item in items:
                    visit_time = item.get("visitTime", "Unknown time")
                    visit_count = item.get("visitCount", 0)
                    result += f"- {item.get('title', 'No title')} - {item.get('url', 'No URL')} (visited {visit_count} times, last: {visit_time})\n"
                
                return result
            
            return f"Unable to query history for: {params.query}"
        
        # Get Recent History Tool
        class HistoryRecentParams(BaseModel):
            """Parameters for getting recent history"""
            count: int = Field(default=10, description="Number of recent items to get")
        
        @self.mcp.tool()
        async def history_get_recent(params: HistoryRecentParams) -> str:
            """Get recent browser history"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.get_recent",
                "data": {
                    "count": params.count
                },
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.websocket_server.send_request_and_wait(request)
            
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
            
            return "Unable to get recent history"
        
        # Delete History Item Tool
        class HistoryDeleteParams(BaseModel):
            """Parameters for deleting a history item"""
            url: str = Field(description="URL of the history item to delete")
        
        @self.mcp.tool()
        async def history_delete_item(params: HistoryDeleteParams) -> str:
            """Delete a specific history item"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.delete_item",
                "data": {
                    "url": params.url
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