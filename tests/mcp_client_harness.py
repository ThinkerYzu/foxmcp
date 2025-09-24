"""
MCP Client Test Harness
A real MCP client that can connect to the FoxMCP server and make tool calls
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

# Optional import - only needed for HTTP MCP client
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class MCPTestClient:
    """A real MCP client for testing the complete chain"""

    def __init__(self, server_host="localhost", server_port=None):
        self.server_host = server_host
        self.server_port = server_port
        if server_port is not None:
            self.base_url = f"http://{server_host}:{server_port}"
        else:
            self.base_url = None  # Will be set when connecting
        self.session = None
        self.connected = False
    
    async def connect(self) -> bool:
        """Connect to the MCP server"""
        if not AIOHTTP_AVAILABLE:
            print("aiohttp not available - cannot use HTTP MCP client")
            return False
            
        try:
            self.session = aiohttp.ClientSession()
            
            # Test connection with a simple request
            async with self.session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    self.connected = True
                    return True
                    
        except Exception as e:
            print(f"Failed to connect to MCP server: {e}")
            
        return False
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available MCP tools"""
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
            
        try:
            async with self.session.post(
                f"{self.base_url}/tools/list",
                json={"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/list"}
            ) as response:
                
                data = await response.json()
                return data.get("result", {}).get("tools", [])
                
        except Exception as e:
            print(f"Failed to list tools: {e}")
            return []
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Call an MCP tool"""
        if not self.connected:
            raise RuntimeError("Not connected to MCP server")
            
        if arguments is None:
            arguments = {}
            
        request_id = str(uuid.uuid4())
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            async with self.session.post(
                f"{self.base_url}/tools/call",
                json=payload
            ) as response:
                
                data = await response.json()
                
                if "error" in data:
                    return {
                        "success": False,
                        "error": data["error"],
                        "content": []
                    }
                
                result = data.get("result", {})
                return {
                    "success": True,
                    "content": result.get("content", []),
                    "isError": result.get("isError", False)
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": []
            }
    
    async def disconnect(self):
        """Disconnect from MCP server"""
        if self.session:
            await self.session.close()
            self.session = None
        self.connected = False


class DirectMCPTestClient:
    """
    Direct MCP client that bypasses HTTP and calls MCP tools directly
    More reliable for testing since it doesn't depend on FastMCP server HTTP endpoints
    """
    
    def __init__(self, mcp_tools_instance):
        self.mcp_tools = mcp_tools_instance
        self.connected = False
    
    async def connect(self) -> bool:
        """Initialize connection (direct access)"""
        self.connected = True
        return True
    
    async def list_tools(self) -> List[str]:
        """List available tool names from actual MCP tools"""
        try:
            # Get actual tool names from FastMCP
            mcp_app = self.mcp_tools.get_mcp_app()
            tools = await mcp_app.get_tools()
            return list(tools.keys())
        except Exception:
            # Fallback to known MCP tool names if FastMCP fails
            return [
                "tabs_list",
                "tabs_create", 
                "tabs_close",
                "tabs_switch",
                "history_query",
                "history_get_recent", 
                "history_delete_item",
                "debug_websocket_status",
                "bookmarks_list",
                "bookmarks_search",
                "bookmarks_create",
                "bookmarks_delete",
                "navigation_back",
                "navigation_forward", 
                "navigation_reload",
                "navigation_go_to_url",
                "content_get_text",
                "content_get_html",
                "content_execute_script"
            ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Call an MCP tool directly via FastMCP"""
        if not self.connected:
            raise RuntimeError("Not connected")
            
        if arguments is None:
            arguments = {}
        
        try:
            # Get the FastMCP app from the MCP tools
            mcp_app = self.mcp_tools.get_mcp_app()
            tools = await mcp_app.get_tools()
            
            # Check if the tool exists
            if tool_name not in tools:
                return {
                    'content': f"Tool '{tool_name}' not found. Available tools: {list(tools.keys())}",
                    'isError': True,
                    'success': False
                }
            
            # Get the tool and call it directly
            tool = tools[tool_name]
            
            try:
                # Call the tool function directly with the arguments
                # FastMCP tools have a fn attribute with the actual function
                result = await tool.fn(**arguments)
                
                return {
                    'content': result,
                    'isError': False,
                    'success': True
                }
                
            except Exception as tool_error:
                return {
                    'content': f"Tool execution error: {tool_error}",
                    'isError': True,
                    'success': False,
                    'error': str(tool_error)
                }
        
        except Exception as e:
            return {
                'content': f"Error calling tool '{tool_name}': {e}",
                'isError': True,
                'success': False,
                'error': str(e)
            }
    
    async def _old_call_tool_websocket(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """OLD METHOD - Call tools via WebSocket (bypasses MCP layer)"""
        if not self.connected:
            raise RuntimeError("Not connected")
            
        if arguments is None:
            arguments = {}
        
        try:
            # Map tool names to actual method calls
            tool_mapping = {
                "list_tabs": self._call_list_tabs,
                "get_active_tab": self._call_get_active_tab,
                "create_tab": self._call_create_tab,
                "close_tab": self._call_close_tab,
                "switch_to_tab": self._call_switch_to_tab,
                "update_tab": self._call_update_tab,
                "get_history": self._call_get_history,
                "history_get_recent": self._call_get_recent_history,
                "debug_websocket_status": self._call_debug_websocket_status,
                "search_history": self._call_search_history,
                "delete_history": self._call_delete_history,
                "list_bookmarks": self._call_list_bookmarks,
                "create_bookmark": self._call_create_bookmark,
                "delete_bookmark": self._call_delete_bookmark,
                "navigate_to": self._call_navigate_to,
                "go_back": self._call_go_back,
                "go_forward": self._call_go_forward,
                "reload_page": self._call_reload_page,
                "get_page_content": self._call_get_page_content,
                "execute_script": self._call_execute_script,
                "take_screenshot": self._call_take_screenshot
            }
            
            if tool_name not in tool_mapping:
                return {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}",
                    "content": []
                }
            
            # Call the tool method
            result = await tool_mapping[tool_name](arguments)
            return {
                "success": True,
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": []
            }
    
    async def _call_list_tabs(self, args: Dict) -> Dict:
        """Call tabs.list through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.list",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_get_active_tab(self, args: Dict) -> Dict:
        """Call tabs.getActive through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request", 
            "action": "tabs.getActive",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_create_tab(self, args: Dict) -> Dict:
        """Call tabs.create through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.create", 
            "data": {
                "url": args.get("url", "about:blank"),
                "active": args.get("active", True)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_close_tab(self, args: Dict) -> Dict:
        """Call tabs.remove through WebSocket"""
        if "tabId" not in args:
            raise ValueError("tabId is required for close_tab")
            
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.remove",
            "data": {"tabId": args["tabId"]},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_switch_to_tab(self, args: Dict) -> Dict:
        """Call tabs.update through WebSocket to switch tabs"""
        if "tabId" not in args:
            raise ValueError("tabId is required for switch_to_tab")
            
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.update",
            "data": {
                "tabId": args["tabId"],
                "active": True
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_update_tab(self, args: Dict) -> Dict:
        """Call tabs.update through WebSocket"""
        if "tabId" not in args:
            raise ValueError("tabId is required for update_tab")
            
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.update",
            "data": args,
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_get_history(self, args: Dict) -> Dict:
        """Call history.search through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "history.search",
            "data": {
                "text": args.get("query", ""),
                "maxResults": args.get("maxResults", 100),
                "startTime": args.get("startTime"),
                "endTime": args.get("endTime")
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_get_recent_history(self, args: Dict) -> Dict:
        """Call history.recent through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "history.recent",
            "data": {
                "count": args.get("count", 10)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_debug_websocket_status(self, args: Dict) -> Dict:
        """Call debug WebSocket status check"""
        # This is a direct call to the server, no WebSocket needed
        try:
            if hasattr(self.mcp_tools.websocket_server, 'connected_clients'):
                client_count = len(getattr(self.mcp_tools.websocket_server, 'connected_clients', []))
                return {"status": f"WebSocket status: {client_count} browser extension(s) connected"}
            else:
                return {"status": "WebSocket server doesn't track connected clients"}
        except Exception as e:
            return {"status": f"WebSocket status check failed: {e}"}
    
    async def _call_search_history(self, args: Dict) -> Dict:
        """Call history.search through WebSocket"""
        return await self._call_get_history(args)
    
    async def _call_delete_history(self, args: Dict) -> Dict:
        """Call history.deleteUrl through WebSocket"""
        if "url" not in args:
            raise ValueError("url is required for delete_history")
            
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "history.deleteUrl",
            "data": {"url": args["url"]},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_list_bookmarks(self, args: Dict) -> Dict:
        """Call bookmarks.getTree through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "bookmarks.getTree",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_create_bookmark(self, args: Dict) -> Dict:
        """Call bookmarks.create through WebSocket"""
        if "title" not in args or "url" not in args:
            raise ValueError("title and url are required for create_bookmark")
            
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "bookmarks.create",
            "data": {
                "title": args["title"],
                "url": args["url"],
                "parentId": args.get("parentId")
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_delete_bookmark(self, args: Dict) -> Dict:
        """Call bookmarks.remove through WebSocket"""
        if "id" not in args:
            raise ValueError("id is required for delete_bookmark")
            
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "bookmarks.remove",
            "data": {"id": args["id"]},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_navigate_to(self, args: Dict) -> Dict:
        """Call tabs.update to navigate to URL"""
        if "url" not in args:
            raise ValueError("url is required for navigate_to")
            
        # Get active tab first, then navigate
        active_tab_request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.query",
            "data": {"active": True, "currentWindow": True},
            "timestamp": datetime.now().isoformat()
        }
        
        active_response = await self.mcp_tools.websocket_server.send_request_and_wait(active_tab_request)
        tabs = active_response.get("data", {}).get("tabs", [])
        
        if not tabs:
            raise RuntimeError("No active tab found")
        
        tab_id = tabs[0]["id"]
        
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.update",
            "data": {
                "tabId": tab_id,
                "url": args["url"]
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_go_back(self, args: Dict) -> Dict:
        """Call tabs.goBack through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.goBack",
            "data": {"tabId": args.get("tabId")},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_go_forward(self, args: Dict) -> Dict:
        """Call tabs.goForward through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.goForward",
            "data": {"tabId": args.get("tabId")},
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_reload_page(self, args: Dict) -> Dict:
        """Call tabs.reload through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.reload",
            "data": {
                "tabId": args.get("tabId"),
                "bypassCache": args.get("bypassCache", False)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_get_page_content(self, args: Dict) -> Dict:
        """Call tabs.executeScript to get page content"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.executeScript",
            "data": {
                "tabId": args.get("tabId"),
                "code": "document.documentElement.outerHTML"
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_execute_script(self, args: Dict) -> Dict:
        """Call tabs.executeScript through WebSocket"""
        if "code" not in args:
            raise ValueError("code is required for execute_script")
            
        request = {
            "id": str(uuid.uuid4()),
            "type": "request",
            "action": "tabs.executeScript",
            "data": {
                "tabId": args.get("tabId"),
                "code": args["code"]
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def _call_take_screenshot(self, args: Dict) -> Dict:
        """Call tabs.captureVisibleTab through WebSocket"""
        request = {
            "id": str(uuid.uuid4()),
            "type": "request", 
            "action": "tabs.captureVisibleTab",
            "data": {
                "format": args.get("format", "png"),
                "quality": args.get("quality", 90)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        response = await self.mcp_tools.websocket_server.send_request_and_wait(request)
        return response.get("data", {})
    
    async def disconnect(self):
        """Disconnect (no-op for direct client)"""
        self.connected = False


if __name__ == "__main__":
    # Test the MCP client harness
    async def test_harness():
        print("Testing MCP Client Harness...")
        
        # This would need a real MCP server running - use dynamic port for testing
        from port_coordinator import PortCoordinator, get_safe_port_range
        coordinator = PortCoordinator(get_safe_port_range('default'))
        test_port = coordinator.find_available_port()
        client = MCPTestClient("localhost", test_port)
        
        try:
            connected = await client.connect()
            if connected:
                print("✓ Connected to MCP server")
                
                tools = await client.list_tools()
                print(f"✓ Found {len(tools)} tools")
                
                # Test a tool call
                result = await client.call_tool("tabs_list")
                print(f"✓ Tool call result: {result}")
                
            else:
                print("✗ Failed to connect to MCP server")
                
        finally:
            await client.disconnect()
    
    # Run test
    asyncio.run(test_harness())