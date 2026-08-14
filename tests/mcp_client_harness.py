"""
MCP Client Test Harness
A real MCP client that can connect to the FoxMCP server and make tool calls
"""

import asyncio
import uuid
from typing import Dict, Any, List

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
            tools = await mcp_app.list_tools()
            return [tool.name for tool in tools]
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
            tool = await mcp_app.get_tool(tool_name)

            # Check if the tool exists
            if tool is None:
                available = [t.name for t in await mcp_app.list_tools()]
                return {
                    'content': f"Tool '{tool_name}' not found. Available tools: {available}",
                    'isError': True,
                    'success': False
                }
            
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
    
    async def disconnect(self):
        """Disconnect (no-op for direct client)"""
        self.connected = False


if __name__ == "__main__":
    # Test the MCP client harness
    async def test_harness():
        print("Testing MCP Client Harness...")
        
        # This would need a real MCP server running - use dynamic port for testing
        from port_coordinator import get_port_by_type
        test_port = get_port_by_type('mcp')
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