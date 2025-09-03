#!/usr/bin/env python3
"""
FoxMCP Server - WebSocket server that bridges browser extension with MCP clients
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

import websockets

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FoxMCPServer:
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.extension_connection = None
        self.pending_requests = {}  # Map of request IDs to Future objects
        
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
    
    async def start_server(self):
        """Start the WebSocket server"""
        logger.info(f"Starting FoxMCP server on {self.host}:{self.port}")
        
        # Use modern websockets API
        server = await websockets.serve(
            self.handle_extension_connection,
            self.host,
            self.port
        )
        
        logger.info("FoxMCP server is running...")
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