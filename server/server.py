#!/usr/bin/env python3
"""
FoxMCP Server - WebSocket server that bridges browser extension with MCP clients

Copyright (c) 2024 FoxMCP Project
Licensed under the MIT License - see LICENSE file for details
"""

import argparse
import asyncio
import json
import logging
import socket
import sys
import os
import threading
from datetime import datetime
from typing import Dict, Any, Optional

import websockets
import uvicorn
try:
    from .mcp_tools import FoxMCPTools
except ImportError:
    from mcp_tools import FoxMCPTools

# Try to import port coordinator for dynamic port allocation
try:
    tests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')
    sys.path.insert(0, tests_dir)
    from port_coordinator import get_port_by_type
    HAS_PORT_COORDINATOR = True
except ImportError:
    HAS_PORT_COORDINATOR = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def find_available_port(start_port=3000, max_attempts=100):
    """Find an available port starting from start_port"""
    if HAS_PORT_COORDINATOR:
        # Use the fixed MCP port if available
        try:
            return get_port_by_type('mcp')
        except Exception:
            pass  # Fall through to traditional approach
    else:
        # Fallback to traditional approach
        for i in range(max_attempts):
            port = start_port + i
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(('localhost', port))
                    return port
            except OSError:
                continue

    raise RuntimeError(f"Could not find available port starting from {start_port}")

class FoxMCPServer:
    def __init__(self, host: str = "localhost", port: int = 8765, mcp_port: int = None, start_mcp: bool = True):
        self.host = host
        self.port = port

        # Set MCP port - default to 3000 for production, dynamic allocation only for tests
        if mcp_port is None:
            # Check if we're in a test environment by checking for pytest or explicit test indicators
            in_test_env = ('pytest' in sys.modules or
                          'PYTEST_CURRENT_TEST' in os.environ or
                          any('pytest' in path or 'test_' in os.path.basename(path) for path in sys.path))
            if in_test_env and HAS_PORT_COORDINATOR:
                # Use dynamic port allocation for tests to avoid conflicts
                self.mcp_port = find_available_port(3000)
            else:
                # Use fixed port 3000 for production
                self.mcp_port = 3000
        else:
            # Check if requested port is available
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(('localhost', mcp_port))
                    self.mcp_port = mcp_port
            except OSError:
                logger.warning(f"Requested MCP port {mcp_port} is in use, finding alternative...")
                self.mcp_port = find_available_port(mcp_port)

        logger.info(f"MCP server will use port {self.mcp_port}")
        self.start_mcp = start_mcp

        # SINGLE CONNECTION CONSTRAINT: Only one extension connection allowed
        self.extension_connection = None
        self.pending_requests = {}  # Map of request IDs to Future objects

        # Connection event management
        self._connection_waiters = []  # List of futures waiting for connection

        # Initialize MCP tools
        self.mcp_tools = FoxMCPTools(self)
        self.mcp_app = self.mcp_tools.get_mcp_app()
        self.mcp_server_task = None
        self.mcp_thread = None
        self.mcp_server_instance = None
        self._shutdown_event = None
        self.websocket_server = None

    async def handle_extension_connection(self, websocket):
        """Handle WebSocket connection from browser extension

        IMPORTANT: Only ONE extension connection is allowed at a time.
        If a new connection arrives, the existing one is closed first.
        This prevents multiple extensions or connection races.
        """
        logger.info(f"Extension connected from {websocket.remote_address}")

        # CONSTRAINT: Only one extension connection allowed at a time
        # Close existing connection if there is one to maintain single connection policy
        if self.extension_connection and self.extension_connection.close_code is None:
            logger.info("Closing existing extension connection for new one")
            try:
                await self.extension_connection.close()
            except Exception as e:
                logger.warning(f"Error closing existing connection: {e}")

        self.extension_connection = websocket

        # Notify all waiters that a connection has been established
        self._notify_connection_waiters()

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

            # Handle debug logs specially - print them prominently
            if message_type == 'debug_log':
                level = data.get('data', {}).get('level', 'log')
                log_message = data.get('data', {}).get('message', '')
                timestamp = data.get('data', {}).get('timestamp', '')

                if level == 'error':
                    print(f"🔴 EXTENSION ERROR [{timestamp}]: {log_message}")
                else:
                    print(f"🔵 EXTENSION LOG [{timestamp}]: {log_message}")
                return

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

    async def send_request_and_wait(self, request: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
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
    async def get_popup_state(self, timeout: float = 30.0) -> Dict[str, Any]:
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

    async def get_options_state(self, timeout: float = 30.0) -> Dict[str, Any]:
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

    async def get_storage_values(self, timeout: float = 30.0) -> Dict[str, Any]:
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

    async def validate_ui_sync(self, expected_values: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
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

    async def refresh_ui_state(self, timeout: float = 30.0) -> Dict[str, Any]:
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

    async def clear_test_history(self, urls: list = None, clear_all: bool = False, timeout: float = 30.0) -> Dict[str, Any]:
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

    async def test_storage_sync_workflow(self, test_values: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
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

    def _notify_connection_waiters(self):
        """Notify all futures waiting for a connection"""
        for future in self._connection_waiters:
            if not future.cancelled():
                future.set_result(True)
        self._connection_waiters.clear()

    async def wait_for_extension_connection(self, timeout: float = 30.0) -> bool:
        """
        Wait for an extension connection to be established.

        Args:
            timeout: Maximum time to wait for connection in seconds

        Returns:
            bool: True if connection was established, False if timeout occurred

        Example:
            # Wait for Firefox extension to connect
            connected = await server.wait_for_extension_connection(timeout=10.0)
            if connected:
                print("Extension connected!")
            else:
                print("Connection timeout")
        """
        # If already connected, return immediately
        if self.extension_connection and self.extension_connection.close_code is None:
            return True

        # Create a future to wait for connection
        connection_future = asyncio.Future()
        self._connection_waiters.append(connection_future)

        try:
            # Wait for connection with timeout
            await asyncio.wait_for(connection_future, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            # Remove the future from waiters if it timed out
            if connection_future in self._connection_waiters:
                self._connection_waiters.remove(connection_future)
            return False
        except Exception:
            # Remove the future from waiters on any other error
            if connection_future in self._connection_waiters:
                self._connection_waiters.remove(connection_future)
            return False

    async def start_mcp_server(self):
        """Start the MCP server in a separate thread"""
        import threading

        # Create shutdown event
        self._shutdown_event = threading.Event()

        def run_mcp_server():
            try:
                logger.info(f"Starting MCP server on {self.host}:{self.mcp_port}")

                # Create server config
                config = uvicorn.Config(
                    self.mcp_app.http_app(),
                    host=self.host,
                    port=self.mcp_port,
                    log_level="error"  # Reduce log noise during tests
                )

                # Create server instance
                self.mcp_server_instance = uvicorn.Server(config)

                # Run server
                self.mcp_server_instance.run()

            except Exception as e:
                logger.warning(f"MCP server failed to start on {self.host}:{self.mcp_port}: {e}")
                # Don't crash the whole server if MCP fails - this is important for tests

        # Run MCP server in separate thread
        self.mcp_thread = threading.Thread(target=run_mcp_server, daemon=True)
        self.mcp_thread.start()
        logger.info(f"MCP server thread started for {self.host}:{self.mcp_port}")

        # Give MCP server time to start (reduced time for faster tests)
        await asyncio.sleep(0.5)

    def _stop_mcp_server(self):
        """Stop the MCP server gracefully"""
        if self.mcp_server_instance:
            try:
                logger.info("Stopping MCP server...")

                # Signal server to shutdown
                self.mcp_server_instance.should_exit = True

                # Wait for thread to finish with timeout
                if self.mcp_thread and self.mcp_thread.is_alive():
                    self.mcp_thread.join(timeout=5.0)

                    if self.mcp_thread.is_alive():
                        logger.warning("MCP server thread did not stop gracefully within timeout")
                    else:
                        logger.info("MCP server stopped gracefully")

                # Clean up references
                self.mcp_server_instance = None
                self.mcp_thread = None

            except Exception as e:
                logger.warning(f"Error stopping MCP server: {e}")

    def _stop_websocket_server(self):
        """Stop the WebSocket server gracefully"""
        if self.websocket_server:
            try:
                logger.info("Stopping WebSocket server...")

                # Close all existing connections first
                if self.extension_connection:
                    try:
                        # Properly close the WebSocket connection (sync call)
                        self.extension_connection.close()
                        logger.info("Extension connection closed")
                    except Exception as e:
                        logger.warning(f"Error closing extension connection: {e}")
                    finally:
                        self.extension_connection = None

                # Close the WebSocket server
                self.websocket_server.close()

                # Clean up reference
                self.websocket_server = None

                logger.info("WebSocket server stopped gracefully")

            except Exception as e:
                logger.warning(f"Error stopping WebSocket server: {e}")

    def _stop(self):
        """Stop all servers (WebSocket and MCP)"""
        logger.info("Stopping FoxMCP server...")

        # Stop MCP server
        self._stop_mcp_server()

        # Stop WebSocket server
        self._stop_websocket_server()

        logger.info("FoxMCP server stopped")

    async def shutdown(self, server_task):
        """
        Gracefully shutdown the server and its task.

        Args:
            server_task: asyncio.Task running the server
        """
        try:
            # Stop server resources first
            self._stop()

            # Cancel the task
            server_task.cancel()

            # Wait for task to finish, handling CancelledError
            try:
                await server_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            logger.warning(f"Error during server shutdown: {e}")

    async def start_server(self):
        """Start both WebSocket and MCP servers"""
        logger.info(f"Starting FoxMCP server on {self.host}:{self.port}")

        # Start MCP server first (if enabled)
        if self.start_mcp:
            await self.start_mcp_server()
            logger.info(f"MCP tools available at http://{self.host}:{self.mcp_port}/")
        else:
            logger.info("MCP server disabled for this instance")

        # Use modern websockets API with SO_REUSEADDR
        import socket
        self.websocket_server = await websockets.serve(
            self.handle_extension_connection,
            self.host,
            self.port,
            reuse_address=True  # Enable SO_REUSEADDR for immediate port reuse
        )

        logger.info("FoxMCP WebSocket server is running...")
        await self.websocket_server.wait_closed()

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='FoxMCP Server - WebSocket server for browser extension')
    parser.add_argument('--host', default='localhost',
                        help='Host to bind to (default: localhost)')
    parser.add_argument('--port', type=int, default=8765,
                        help='WebSocket port (default: 8765)')
    parser.add_argument('--mcp-port', type=int, default=None,
                        help='MCP server port (default: 3000, dynamic allocation in tests)')
    parser.add_argument('--no-mcp', action='store_true',
                        help='Disable MCP server')

    args = parser.parse_args()

    # Ensure localhost-only binding for security
    if args.host != 'localhost' and args.host != '127.0.0.1':
        logger.warning(f"Host '{args.host}' changed to 'localhost' for security")
        args.host = 'localhost'

    server = FoxMCPServer(
        host=args.host,
        port=args.port,
        mcp_port=args.mcp_port,
        start_mcp=not args.no_mcp
    )
    await server.start_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
