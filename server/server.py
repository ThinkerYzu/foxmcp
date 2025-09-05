#!/usr/bin/env python3
"""
FoxMCP Server - WebSocket server that bridges browser extension with MCP clients
"""

import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional

import websockets
import uvicorn
try:
    from .mcp_tools import FoxMCPTools
except ImportError:
    from mcp_tools import FoxMCPTools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FoxMCPServer:
    def __init__(self, host: str = "localhost", port: int = 8765, mcp_port: int = 3000, start_mcp: bool = True):
        self.host = host
        self.port = port
        self.mcp_port = mcp_port
        self.start_mcp = start_mcp
        self.extension_connection = None
        self.pending_requests = {}  # Map of request IDs to Future objects
        
        # Initialize MCP tools
        self.mcp_tools = FoxMCPTools(self)
        self.mcp_app = self.mcp_tools.get_mcp_app()
        self.mcp_server_task = None
        
    async def handle_extension_connection(self, websocket):
        """Handle WebSocket connection from browser extension"""
        logger.info(f"Extension connected from {websocket.remote_address}")
        self.extension_connection = websocket
        
        try:
            async for message in websocket:
                await self.handle_extension_message(message)
        except ConnectionAbortedError:
            logger.info("Extension disconnected")
        except Exception as e:
            logger.error(f"Error handling extension connection: {e}")
        finally:
            self.extension_connection = None
    
    async def handle_extension_message(self, message: str):
        """Process message from browser extension"""
        try:
            data = json.loads(message)
            message_type = data.get('type', 'unknown')
            message_id = data.get('id')
            action = data.get('action', 'unknown')
            
            logger.info(f"Received from extension: {message_type} - {action} (ID: {message_id})")
            
            if message_type == 'request':
                # Handle ping-pong for connection testing
                if action == 'ping':
                    await self.handle_ping_request(data)
                    return
            
            elif message_type in ['response', 'error']:
                # Handle response/error from extension
                await self.handle_extension_response(data)
                return
            
            # For other message types, just log for now
            logger.warning(f"Unhandled message type: {message_type}")
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {message}")
        except Exception as e:
            logger.error(f"Error processing extension message: {e}")
    
    async def handle_extension_response(self, response_data: Dict[str, Any]):
        """Handle response or error from browser extension"""
        request_id = response_data.get('id')
        if not request_id:
            logger.warning("Received response without ID")
            return
            
        if request_id in self.pending_requests:
            future = self.pending_requests.pop(request_id)
            if not future.cancelled():
                future.set_result(response_data)
                logger.info(f"Completed pending request: {request_id}")
        else:
            logger.warning(f"Received response for unknown request: {request_id}")
    
    async def handle_ping_request(self, request: Dict[str, Any]):
        """Handle ping request from extension"""
        response = {
            "id": request["id"],
            "type": "request", 
            "action": "ping",
            "data": {"test": True},
            "timestamp": datetime.now().isoformat()
        }
        
        success = await self.send_to_extension(response)
        if success:
            logger.info(f"Sent ping request to extension: {request['id']}")
        else:
            logger.error(f"Failed to send ping request: {request['id']}")
    
    async def test_ping_extension(self) -> Dict[str, Any]:
        """Send ping to extension and wait for response"""
        if not self.extension_connection:
            return {"success": False, "error": "No extension connection"}
        
        test_id = f"server_ping_{int(datetime.now().timestamp() * 1000)}"
        ping_request = {
            "id": test_id,
            "type": "request",
            "action": "ping", 
            "data": {"server_test": True},
            "timestamp": datetime.now().isoformat()
        }
        
        # Send ping and return immediately (for now)
        success = await self.send_to_extension(ping_request)
        if success:
            return {"success": True, "message": "Ping sent to extension", "id": test_id}
        else:
            return {"success": False, "error": "Failed to send ping"}
    
    async def send_to_extension(self, message: Dict[str, Any]) -> bool:
        """Send message to browser extension"""
        if not self.extension_connection:
            logger.warning("No extension connection available")
            return False
        
        try:
            message['timestamp'] = datetime.now().isoformat()
            await self.extension_connection.send(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Error sending to extension: {e}")
            return False
    
    async def send_request_and_wait(self, request: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        """Send request to extension and wait for response"""
        request_id = request.get('id')
        if not request_id:
            raise ValueError("Request must have an ID")
        
        if not self.extension_connection:
            return {"error": "No extension connection available"}
        
        # Create future for response
        response_future = asyncio.Future()
        self.pending_requests[request_id] = response_future
        
        try:
            # Send the request
            success = await self.send_to_extension(request)
            if not success:
                self.pending_requests.pop(request_id, None)
                return {"error": "Failed to send request to extension"}
            
            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=timeout)
            return response
            
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            return {"error": f"Request timed out after {timeout} seconds"}
        except Exception as e:
            self.pending_requests.pop(request_id, None)
            return {"error": f"Request failed: {str(e)}"}
    
    # Test Helper Methods
    async def get_popup_state(self, timeout: float = 5.0) -> Dict[str, Any]:
        """Get current popup display state from extension"""
        request = {
            "id": f"test_popup_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.get_popup_state",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait(request, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response
    
    async def get_options_state(self, timeout: float = 5.0) -> Dict[str, Any]:
        """Get current options page display state from extension"""
        request = {
            "id": f"test_options_{datetime.now().isoformat()}",
            "type": "request", 
            "action": "test.get_options_state",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait(request, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response
    
    async def get_storage_values(self, timeout: float = 5.0) -> Dict[str, Any]:
        """Get raw storage.sync values from extension"""
        request = {
            "id": f"test_storage_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.get_storage_values", 
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait(request, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response
    
    async def validate_ui_sync(self, expected_values: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
        """Validate UI-storage synchronization with expected values"""
        request = {
            "id": f"test_validate_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.validate_ui_sync",
            "data": {"expectedValues": expected_values},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait(request, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response
    
    async def refresh_ui_state(self, timeout: float = 5.0) -> Dict[str, Any]:
        """Trigger UI state refresh in extension"""
        request = {
            "id": f"test_refresh_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.refresh_ui_state",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait(request, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response
    
    async def visit_url_for_test(self, url: str, wait_time: float = 6.0, timeout: float = 20.0) -> Dict[str, Any]:
        """Visit a URL to create browser history entry for testing"""
        request = {
            "id": f"test_visit_url_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.visit_url",
            "data": {
                "url": url,
                "waitTime": int(wait_time * 1000)  # Convert to milliseconds
            },
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait(request, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response
    
    async def visit_multiple_urls_for_test(self, urls: list, wait_time: float = 6.0, delay_between: float = 2.0, timeout: float = 90.0) -> Dict[str, Any]:
        """Visit multiple URLs to create browser history entries for testing"""
        request = {
            "id": f"test_visit_multiple_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.visit_multiple_urls",
            "data": {
                "urls": urls,
                "waitTime": int(wait_time * 1000),  # Convert to milliseconds
                "delayBetween": int(delay_between * 1000)  # Convert to milliseconds
            },
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait(request, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response
    
    async def clear_test_history(self, urls: list = None, clear_all: bool = False, timeout: float = 10.0) -> Dict[str, Any]:
        """Clear test history entries for cleanup"""
        request = {
            "id": f"test_clear_history_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.clear_test_history",
            "data": {
                "urls": urls or [],
                "clearAll": clear_all
            },
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait(request, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response

    async def test_storage_sync_workflow(self, test_values: Dict[str, Any], timeout: float = 10.0) -> Dict[str, Any]:
        """Complete test workflow: set values, validate sync, return results"""
        results = {
            "workflow_success": False,
            "steps": {},
            "errors": []
        }
        
        try:
            # Step 1: Get initial state
            initial_storage = await self.get_storage_values(timeout)
            if "error" in initial_storage:
                results["errors"].append(f"Failed to get initial storage: {initial_storage['error']}")
                return results
            results["steps"]["initial_storage"] = initial_storage
            
            # Step 2: Get popup state
            popup_state = await self.get_popup_state(timeout)
            if "error" in popup_state:
                results["errors"].append(f"Failed to get popup state: {popup_state['error']}")
                return results
            results["steps"]["popup_state"] = popup_state
            
            # Step 3: Get options state
            options_state = await self.get_options_state(timeout)
            if "error" in options_state:
                results["errors"].append(f"Failed to get options state: {options_state['error']}")
                return results
            results["steps"]["options_state"] = options_state
            
            # Step 4: Validate synchronization
            validation_result = await self.validate_ui_sync(test_values, timeout)
            if "error" in validation_result:
                results["errors"].append(f"Failed to validate UI sync: {validation_result['error']}")
                return results
            results["steps"]["validation"] = validation_result
            
            # Check if validation passed
            if validation_result.get("popupSyncValid") and validation_result.get("optionsSyncValid") and validation_result.get("storageMatches"):
                results["workflow_success"] = True
            else:
                results["errors"].extend(validation_result.get("issues", []))
                
            return results
            
        except Exception as e:
            results["errors"].append(f"Workflow exception: {str(e)}")
            return results
    
    async def start_mcp_server(self):
        """Start the MCP server in a separate thread"""
        def run_mcp_server():
            try:
                logger.info(f"Starting MCP server on port {self.mcp_port}")
                uvicorn.run(
                    self.mcp_app,
                    host="0.0.0.0",
                    port=self.mcp_port,
                    log_level="error"  # Reduce log noise during tests
                )
            except Exception as e:
                logger.warning(f"MCP server failed to start on port {self.mcp_port}: {e}")
                # Don't crash the whole server if MCP fails - this is important for tests
        
        # Run MCP server in separate thread
        mcp_thread = threading.Thread(target=run_mcp_server, daemon=True)
        mcp_thread.start()
        logger.info(f"MCP server thread started for port {self.mcp_port}")
        
        # Give MCP server time to start (reduced time for faster tests)
        await asyncio.sleep(0.5)
    
    async def start_server(self):
        """Start both WebSocket and MCP servers"""
        logger.info(f"Starting FoxMCP server on {self.host}:{self.port}")
        
        # Start MCP server first (if enabled)
        if self.start_mcp:
            await self.start_mcp_server()
            logger.info(f"MCP tools available at http://localhost:{self.mcp_port}/")
        else:
            logger.info("MCP server disabled for this instance")
        
        # Use modern websockets API
        server = await websockets.serve(
            self.handle_extension_connection,
            self.host,
            self.port
        )
        
        logger.info("FoxMCP WebSocket server is running...")
        await server.wait_closed()

async def main():
    """Main entry point"""
    server = FoxMCPServer()
    await server.start_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")