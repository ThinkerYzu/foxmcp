"""
MCP Handler - Implements FastMCP integration
"""

from typing import Dict, Any, List, Optional
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class MCPHandler:
    """Handles MCP protocol integration with FastMCP"""
    
    def __init__(self, server_instance):
        self.server = server_instance
        self.tools = self._register_tools()
    
    def _register_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register all available MCP tools"""
        return {
            # History tools
            "browser_history_query": {
                "description": "Search browser history",
                "parameters": {
                    "query": {"type": "string", "description": "Search query"},
                    "maxResults": {"type": "integer", "description": "Maximum results", "default": 50},
                    "startTime": {"type": "string", "description": "Start time (ISO format)"},
                    "endTime": {"type": "string", "description": "End time (ISO format)"}
                }
            },
            "browser_history_recent": {
                "description": "Get recent browser history",
                "parameters": {
                    "count": {"type": "integer", "description": "Number of items", "default": 10}
                }
            },
            
            # Tab tools
            "browser_tabs_list": {
                "description": "List all open browser tabs",
                "parameters": {}
            },
            "browser_tabs_create": {
                "description": "Create a new browser tab",
                "parameters": {
                    "url": {"type": "string", "description": "URL to open"},
                    "active": {"type": "boolean", "description": "Make tab active", "default": True}
                }
            },
            "browser_tabs_close": {
                "description": "Close a browser tab",
                "parameters": {
                    "tabId": {"type": "integer", "description": "Tab ID to close"}
                }
            },
            
            # Content tools
            "browser_content_text": {
                "description": "Get text content from browser tab",
                "parameters": {
                    "tabId": {"type": "integer", "description": "Tab ID"}
                }
            },
            "browser_content_html": {
                "description": "Get HTML content from browser tab", 
                "parameters": {
                    "tabId": {"type": "integer", "description": "Tab ID"}
                }
            },
            
            # Navigation tools
            "browser_navigate_url": {
                "description": "Navigate browser tab to URL",
                "parameters": {
                    "tabId": {"type": "integer", "description": "Tab ID"},
                    "url": {"type": "string", "description": "URL to navigate to"}
                }
            },
            "browser_navigate_back": {
                "description": "Navigate back in browser history",
                "parameters": {
                    "tabId": {"type": "integer", "description": "Tab ID"}
                }
            },
            
            # Bookmark tools
            "browser_bookmarks_list": {
                "description": "List browser bookmarks",
                "parameters": {
                    "folderId": {"type": "string", "description": "Folder ID", "default": "1"}
                }
            },
            "browser_bookmarks_create": {
                "description": "Create a new bookmark",
                "parameters": {
                    "title": {"type": "string", "description": "Bookmark title"},
                    "url": {"type": "string", "description": "Bookmark URL"},
                    "parentId": {"type": "string", "description": "Parent folder ID", "default": "1"}
                }
            }
        }
    
    async def handle_tool_call(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP tool call by forwarding to browser extension"""
        if tool_name not in self.tools:
            return {"error": f"Unknown tool: {tool_name}"}
        
        # Map MCP tool names to WebSocket actions
        action_map = {
            "browser_history_query": "history.query",
            "browser_history_recent": "history.recent",
            "browser_tabs_list": "tabs.list",
            "browser_tabs_create": "tabs.create",
            "browser_tabs_close": "tabs.close",
            "browser_content_text": "content.text",
            "browser_content_html": "content.html",
            "browser_navigate_url": "navigation.go",
            "browser_navigate_back": "navigation.back",
            "browser_bookmarks_list": "bookmarks.list",
            "browser_bookmarks_create": "bookmarks.create"
        }
        
        action = action_map.get(tool_name)
        if not action:
            return {"error": f"No action mapping for tool: {tool_name}"}
        
        # Generate unique request ID
        request_id = f"mcp_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp() * 1000)}"
        
        # Create request for extension
        request = {
            "id": request_id,
            "type": "request", 
            "action": action,
            "data": parameters,
            "timestamp": datetime.now().isoformat()
        }
        
        # Send request and wait for response
        logger.info(f"Sending MCP request {tool_name} -> {action} (ID: {request_id})")
        response = await self.server.send_request_and_wait(request, timeout=15.0)
        
        # Handle different response types
        if "error" in response:
            logger.error(f"MCP request failed: {response['error']}")
            return {"error": response["error"]}
        
        response_type = response.get("type")
        if response_type == "error":
            error_data = response.get("data", {})
            return {"error": f"{error_data.get('code', 'UNKNOWN')}: {error_data.get('message', 'Unknown error')}"}
        
        elif response_type == "response":
            logger.info(f"MCP request completed: {tool_name} (ID: {request_id})")
            return response.get("data", {})
        
        else:
            logger.warning(f"Unexpected response type: {response_type}")
            return {"error": f"Unexpected response type: {response_type}"}
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available MCP tools"""
        return [
            {
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"]
            }
            for name, tool in self.tools.items()
        ]