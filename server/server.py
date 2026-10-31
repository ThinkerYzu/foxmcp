#!/usr/bin/env python3
"""
FoxMCP Server - WebSocket server that bridges browser extension with MCP clients

Copyright (c) 2024 FoxMCP Project
Licensed under the MIT License - see LICENSE file for details
"""

import argparse
from collections import Counter
from contextlib import suppress
import asyncio
import json
import logging
import socket
import sys
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

import websockets
import uvicorn
try:
    from .version import VERSION
    from .mcp_tools import FoxMCPTools
    from .file_transfer import FileTransferServer
    from .browser_proxy import BrowserProxyHub, EXTENSION_ORIGIN_PATTERN, PROTOCOL_VERSION
    from .browser_profile import BrowserProfile
    from .profile_names import FirefoxProfileNames
except ImportError:
    from version import VERSION
    from mcp_tools import FoxMCPTools
    from file_transfer import FileTransferServer
    from browser_proxy import BrowserProxyHub, EXTENSION_ORIGIN_PATTERN, PROTOCOL_VERSION
    from browser_profile import BrowserProfile
    from profile_names import FirefoxProfileNames

# Try to import port coordinator for dynamic port allocation
try:
    tests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')
    sys.path.insert(0, tests_dir)
    from port_coordinator import get_port_by_type
    HAS_PORT_COORDINATOR = True
except ImportError:
    HAS_PORT_COORDINATOR = False

# Configure logging
#
# stderr is already basicConfig's default, but it is named here because with
# --stdio the process speaks JSON-RPC over stdout: a single log line written
# there breaks the framing and the client drops the connection. Anything in
# this process that has something to say says it on stderr.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

# Only browser extensions may open the extension WebSocket at `/`.
#
# WebSocket handshakes are exempt from the same-origin policy and are never
# preflighted, so without this any web page the user visits could connect to
# the localhost port and be accepted as the extension. Binding to localhost
# does not exclude web pages: they reach it from inside the user's own browser.
#
# The check is on the scheme rather than a whole origin because Firefox
# generates the extension's UUID per install, so no fixed value would work for
# more than one profile. A page's origin is always http:// or https://, which
# the pattern excludes, and page JavaScript cannot suppress or forge it.
#
# BrowserProxyHub applies separate checks to `/discovery` and `/proxy` before
# either can reach the extension handler. Local proxies have no Origin header.

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
    # How often to check whether the MCP clients owning monitors are still there
    MONITOR_REAP_INTERVAL = 5.0

    def __init__(self, host: str = "localhost", port: int = 8765, mcp_port: int = None, start_mcp: bool = True,
                 disabled_tool_groups=None, enabled_tools=None, use_stdio: bool = False):
        self.host = host
        self.port = port
        self.use_stdio = use_stdio

        # In stdio mode the MCP side has no listener, so there is no port to pick.
        # Running the selection anyway would bind-test a port nothing serves and
        # report "port in use" against whatever else holds 3000 - most likely the
        # user's own HTTP-mode server, which is not a conflict at all here.
        if use_stdio:
            self.mcp_port = None
        # Set MCP port - default to 3000 for production, dynamic allocation only for tests
        elif mcp_port is None:
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

        if self.mcp_port is not None:
            logger.info(f"MCP server will use port {self.mcp_port}")
        self.start_mcp = start_mcp

        self.profiles = {}
        self._next_profile_id = 1
        self.profile_names = FirefoxProfileNames()

        # Connection event management
        self._connection_waiters = []  # List of futures waiting for connection

        # Initialize MCP tools
        self.file_transfers = FileTransferServer()
        self.mcp_tools = FoxMCPTools(self, disabled_groups=disabled_tool_groups,
                                     enabled_tools=enabled_tools)
        self.mcp_app = self.mcp_tools.get_mcp_app()
        self.mcp_server_task = None
        self.mcp_thread = None
        self.mcp_server_instance = None

        self.mcp_http_app = None
        self.monitor_reaper_task = None
        self._shutdown_event = None
        self.websocket_server = None
        self._browser_loop = None
        self.browser_hub = BrowserProxyHub(self)

    def log_rejected_handshake(self, connection, request, response):
        """Log handshakes the library refused, and let the refusal stand

        Registered as the `process_response` hook so that origin rejections are
        visible. The library rejects them with a 403 but logs only at debug
        level, which would make a legitimate extension that stopped connecting
        indistinguishable from a server that was never reached at all.

        Always returns None, meaning "use the response you already built" - this
        hook observes, it never decides.
        """
        if response.status_code == 403:
            origin = request.headers.get_all('Origin')
            logger.warning(
                f"Rejected request to {request.path} from Origin {origin!r}"
            )
        return None

    async def handle_extension_connection(self, websocket):
        """Register a ready profile without displacing any connected profile."""
        profile = None
        try:
            await websocket.send(json.dumps({"type": "hello", "data": {
                "version": VERSION, "protocol_version": PROTOCOL_VERSION}}))
            hello = json.loads(await asyncio.wait_for(websocket.recv(), 5.0))
            data = hello.get("data") if isinstance(hello, dict) else None
            if (not isinstance(data, dict) or hello.get("type") != "hello"
                    or type(data.get("protocol_version")) is not int
                    or data["protocol_version"] != PROTOCOL_VERSION):
                logger.warning("Rejected extension: protocol %s required; update extension", PROTOCOL_VERSION)
                await websocket.close(code=1008, reason=f"FoxMCP protocol {PROTOCOL_VERSION} required; update extension")
                return
            profile_id = self._next_profile_id
            self._next_profile_id += 1
            origin = websocket.request.headers.get("Origin", "")
            profile = BrowserProfile(self, websocket, profile_id, origin)
            self.profiles[profile_id] = profile
            await profile.handle_extension_message(json.dumps(hello))
            if profile.extension_version is None:
                logger.warning("Extension version unavailable for profile %s; browser tools remain available", profile_id)
            await websocket.send(json.dumps({"type": "ready", "data": {}}))
            self._notify_connection_waiters()
            logger.info("Firefox profile %s connected from %s", profile_id, websocket.remote_address)
            async for message in websocket:
                if self.profiles.get(profile_id) is not profile:
                    break
                await profile.handle_extension_message(message)
        except (ValueError, TypeError, asyncio.TimeoutError):
            logger.warning("Rejected invalid or timed-out Firefox profile handshake")
            await websocket.close(code=1008, reason="Invalid FoxMCP profile handshake; update extension")
        except websockets.ConnectionClosed:
            pass
        finally:
            if profile is not None:
                profile.disconnected()
                if self.profiles.get(profile.profile_id) is profile:
                    self.profiles.pop(profile.profile_id)

    async def get_extension_status(self):
        """Report all live profiles, without choosing a target implicitly."""
        snapshot = await self.list_profiles(populate=False, include_windows=False)
        if not snapshot["profiles"]:
            return "No browser extension is connected"
        return "Browser extension connected profiles:\n" + "\n".join(
            f"- {p['profile_id']}: {p['name'] or 'name unavailable'}" for p in snapshot["profiles"])

    async def list_profiles(self, populate=True, include_windows=True):
        """Discover every profile; a failed peer cannot hide healthy peers."""
        if self._browser_loop is not None and asyncio.get_running_loop() is not self._browser_loop:
            return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
                self.list_profiles(populate, include_windows), self._browser_loop))
        profiles = [p for p in self.profiles.values() if p.extension_connection.close_code is None]
        if not profiles:
            return {"profiles": []}
        origins = Counter(p.origin for p in profiles)
        try:
            names = await asyncio.to_thread(self.profile_names.resolve, [p.origin for p in profiles])
        except (OSError, ValueError, RuntimeError) as error:
            names = {p.origin: {"name": None, "name_error":
                     f"Firefox profile metadata unavailable: {type(error).__name__}"} for p in profiles}
        for origin, count in origins.items():
            if count > 1:
                names[origin] = {"name": None, "name_error":
                    "Multiple connected Firefox instances share this extension Origin; name is ambiguous"}

        async def describe(profile):
            result = {"profile_id": profile.profile_id, "extension_version": profile.extension_version,
                      **names[profile.origin]}
            if include_windows:
                response = await profile.send_request_and_wait({
                    "id": uuid.uuid4().hex, "type": "request", "action": "windows.list",
                    "data": {"populate": populate}}, timeout=5.0)
                payload = response.get("data")
                windows = payload.get("windows") if isinstance(payload, dict) else None
                result["windows"] = windows if isinstance(windows, list) else []
                if "error" in response or response.get("type") == "error":
                    result["error"] = response.get("error") or payload
                elif not isinstance(windows, list):
                    result["error"] = "Invalid windows response from Firefox profile"
            return result

        return {"profiles": list(await asyncio.gather(*(describe(p) for p in profiles)))}

    async def send_request_and_wait(self, request, timeout=30.0):
        """Route one command to its explicit profile on the browser event loop."""
        if self._browser_loop is not None and asyncio.get_running_loop() is not self._browser_loop:
            return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
                self.send_request_and_wait(request, timeout), self._browser_loop))
        profile_id = request.get("profile_id")
        if type(profile_id) is not int or profile_id < 1:
            return {"error": "profile_id is required and must be a positive integer; call profiles_list first"}
        profile = self.profiles.get(profile_id)
        if profile is None or profile.extension_connection.close_code is not None:
            return {"error": "Firefox profile is not connected; call profiles_list again", "profile_id": profile_id}
        return await profile.send_request_and_wait(request, timeout)

    def register_monitor(self, profile_id, monitor_id, session_id, connection_id):
        """Record ownership only on the connection that created the monitor."""
        if self._browser_loop is not None:
            try:
                same_loop = asyncio.get_running_loop() is self._browser_loop
            except RuntimeError:
                same_loop = False
            if not same_loop:
                self._browser_loop.call_soon_threadsafe(
                    self.register_monitor, profile_id, monitor_id, session_id, connection_id)
                return
        profile = self.profiles.get(profile_id)
        if profile is not None and profile.connection_id == connection_id:
            profile.register_monitor(monitor_id, session_id)

    def forget_monitor(self, profile_id, monitor_id, connection_id):
        """Forget a monitor without touching a reconnected profile's state."""
        if self._browser_loop is not None:
            try:
                same_loop = asyncio.get_running_loop() is self._browser_loop
            except RuntimeError:
                same_loop = False
            if not same_loop:
                self._browser_loop.call_soon_threadsafe(
                    self.forget_monitor, profile_id, monitor_id, connection_id)
                return
        profile = self.profiles.get(profile_id)
        if profile is not None and profile.connection_id == connection_id:
            profile.forget_monitor(monitor_id)

    async def stop_monitors_of_gone_clients(self):
        """Reap abandoned monitors independently for each profile."""
        await asyncio.gather(*(p.stop_monitors_of_gone_clients() for p in list(self.profiles.values())))

    async def _reap_monitors(self):
        """Poll for departed MCP clients for as long as the server runs

        Polling rather than a callback because the MCP SDK offers no hook for a
        session ending. Only started in HTTP mode: under --stdio the server has
        the one client, and when it goes the process goes with it, which drops the
        WebSocket and lets the extension clear its own monitors.
        """
        while True:
            await asyncio.sleep(self.MONITOR_REAP_INTERVAL)
            try:
                await self.stop_monitors_of_gone_clients()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Error reaping monitors of departed clients: {e}")

    # Test Helper Methods
    async def get_popup_state(self, profile_id: int, timeout: float = 30.0) -> Dict[str, Any]:
        """Get current popup display state from extension"""
        request = {
            "id": f"test_popup_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.get_popup_state",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait({**request, "profile_id": profile_id}, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response

    async def get_options_state(self, profile_id: int, timeout: float = 30.0) -> Dict[str, Any]:
        """Get current options page display state from extension"""
        request = {
            "id": f"test_options_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.get_options_state",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait({**request, "profile_id": profile_id}, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response

    async def get_storage_values(self, profile_id: int, timeout: float = 30.0) -> Dict[str, Any]:
        """Get raw storage.sync values from extension"""
        request = {
            "id": f"test_storage_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.get_storage_values",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait({**request, "profile_id": profile_id}, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response

    async def validate_ui_sync(self, profile_id: int, expected_values: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """Validate UI-storage synchronization with expected values"""
        request = {
            "id": f"test_validate_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.validate_ui_sync",
            "data": {"expectedValues": expected_values},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait({**request, "profile_id": profile_id}, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response

    async def refresh_ui_state(self, profile_id: int, timeout: float = 30.0) -> Dict[str, Any]:
        """Trigger UI state refresh in extension"""
        request = {
            "id": f"test_refresh_{datetime.now().isoformat()}",
            "type": "request",
            "action": "test.refresh_ui_state",
            "data": {},
            "timestamp": datetime.now().isoformat()
        }
        response = await self.send_request_and_wait({**request, "profile_id": profile_id}, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response

    async def visit_url_for_test(self, profile_id: int, url: str, wait_time: float = 6.0, timeout: float = 20.0) -> Dict[str, Any]:
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
        response = await self.send_request_and_wait({**request, "profile_id": profile_id}, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response

    async def visit_multiple_urls_for_test(self, profile_id: int, urls: list, wait_time: float = 6.0, delay_between: float = 2.0, timeout: float = 90.0) -> Dict[str, Any]:
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
        response = await self.send_request_and_wait({**request, "profile_id": profile_id}, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response

    async def clear_test_history(self, profile_id: int, urls: list = None, clear_all: bool = False, timeout: float = 30.0) -> Dict[str, Any]:
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
        response = await self.send_request_and_wait({**request, "profile_id": profile_id}, timeout)
        return response.get('data', response) if isinstance(response, dict) and 'data' in response else response

    async def test_storage_sync_workflow(self, profile_id: int, test_values: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """Complete test workflow: set values, validate sync, return results"""
        results = {
            "workflow_success": False,
            "steps": {},
            "errors": []
        }

        try:
            # Step 1: Get initial state
            initial_storage = await self.get_storage_values(profile_id, timeout)
            if "error" in initial_storage:
                results["errors"].append(f"Failed to get initial storage: {initial_storage['error']}")
                return results
            results["steps"]["initial_storage"] = initial_storage

            # Step 2: Get popup state
            popup_state = await self.get_popup_state(profile_id, timeout)
            if "error" in popup_state:
                results["errors"].append(f"Failed to get popup state: {popup_state['error']}")
                return results
            results["steps"]["popup_state"] = popup_state

            # Step 3: Get options state
            options_state = await self.get_options_state(profile_id, timeout)
            if "error" in options_state:
                results["errors"].append(f"Failed to get options state: {options_state['error']}")
                return results
            results["steps"]["options_state"] = options_state

            # Step 4: Validate synchronization
            validation_result = await self.validate_ui_sync(profile_id, test_values, timeout)
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
        if any(p.extension_connection.close_code is None for p in self.profiles.values()):
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
                self.mcp_http_app = self.mcp_app.http_app()
                config = uvicorn.Config(
                    self.mcp_http_app,
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

    async def _stop_websocket_server(self):
        """
        Stop the WebSocket server and wait for its listening socket to be released.

        Must be awaited: both the connection close and the server shutdown are
        coroutines, and returning before they finish leaves the port bound. The
        next server to bind that port then fails, which in the test suite shows
        up as a client connecting to the old listener and timing out on the
        handshake rather than as an obvious "address already in use".
        """
        if self.websocket_server:
            try:
                logger.info("Stopping WebSocket server...")

                # Each handler cleans up only the profile it owns.
                await asyncio.gather(*(p.extension_connection.close() for p in list(self.profiles.values())),
                                     return_exceptions=True)

                # close() only starts the shutdown; wait_closed() is what
                # actually releases the port. Bounded so a connection that
                # refuses to close cannot hang the caller forever.
                self.websocket_server.close()
                try:
                    await asyncio.wait_for(self.websocket_server.wait_closed(), timeout=5.0)
                    logger.info("WebSocket server stopped gracefully")
                except asyncio.TimeoutError:
                    logger.warning("WebSocket server did not release its port within timeout")

                # Clean up reference
                self.websocket_server = None

            except Exception as e:
                logger.warning(f"Error stopping WebSocket server: {e}")

    async def _stop(self):
        """Stop all servers (WebSocket and MCP)"""
        logger.info("Stopping FoxMCP server...")

        if self.monitor_reaper_task:
            self.monitor_reaper_task.cancel()
            try:
                await self.monitor_reaper_task
            except asyncio.CancelledError:
                pass
            self.monitor_reaper_task = None

        # Stop MCP server
        self._stop_mcp_server()

        # Stop WebSocket server
        await self._stop_websocket_server()

        await asyncio.to_thread(self.file_transfers.close)

        logger.info("FoxMCP server stopped")

    async def shutdown(self, server_task):
        """
        Gracefully shutdown the server and its task.

        Args:
            server_task: asyncio.Task running the server
        """
        try:
            # Stop server resources first
            await self._stop()

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

        # Own the browser port before starting an MCP listener. A failed bind
        # must not leave an unrelated HTTP listener alive in a losing process.
        await self.start_browser_listener()

        # Start MCP server (if enabled)
        #
        # stdio is the exception, and starts below instead: HTTP mode hands
        # uvicorn a thread and returns, while the stdio transport runs in this
        # loop until the client hangs up. Awaiting it here would mean never
        # reaching the WebSocket server it depends on.
        if self.start_mcp and not self.use_stdio:
            await self.start_mcp_server()
            logger.info(f"MCP tools available at http://{self.host}:{self.mcp_port}/")
        elif not self.start_mcp:
            logger.info("MCP server disabled for this instance")

        if self.start_mcp and not self.use_stdio:
            self.monitor_reaper_task = asyncio.create_task(self._reap_monitors())

        if self.start_mcp and self.use_stdio:
            await self._serve_mcp_over_stdio()
        else:
            await self.websocket_server.wait_closed()

    async def start_browser_listener(self):
        """Bind the common discovery, proxy and extension port atomically."""
        self._browser_loop = asyncio.get_running_loop()
        try:
            self.websocket_server = await websockets.serve(
                self.browser_hub.handle_connection,
                self.host,
                self.port,
                # Windows SO_REUSEADDR permits stealing an occupied listening
                # port; Unix needs it to reuse a port after a clean shutdown.
                reuse_address=os.name != 'nt',
                # Rejected during the handshake, so a non-extension client never
                # reaches handle_extension_connection - which would otherwise close
                # the real extension's socket to make room for it.
                origins=[EXTENSION_ORIGIN_PATTERN, None],
                process_request=self.browser_hub.process_request,
                process_response=self.log_rejected_handshake
            )
        except OSError as e:
            # The extension reaches one fixed port, so only one server can hold
            # it. That is easy to hit in stdio mode, where every MCP client
            # launches a server of its own, and the bare errno does not say so.
            logger.error(
                f"Cannot listen on {self.host}:{self.port} for the extension: {e}. "
                "Another FoxMCP server is most likely already running - the "
                "extension connects to one port, so only one server can serve it."
            )
            raise

        logger.info("FoxMCP WebSocket server is running...")

    async def _serve_mcp_over_stdio(self):
        """Serve MCP on stdin/stdout until the client hangs up, then release the port

        Only reached with --stdio, and only after the WebSocket server is
        listening. Returns when either side finishes: the client closing stdin
        is the normal end, and a WebSocket server that stops is a reason to stop
        answering tool calls it can no longer carry out.

        Unlike HTTP mode, the MCP server runs as a task in this loop rather than
        in a uvicorn thread, because the stdio transport is asyncio all the way
        down and has no thread of its own to run in.
        """
        logger.info("MCP serving over stdio; no MCP HTTP listener")

        # show_banner=False keeps startup off the network as well as quiet: the
        # banner asks PyPI whether a newer fastmcp exists, which is a delay a
        # client is waiting on and a request the user did not ask for.
        mcp_task = asyncio.create_task(
            self.mcp_app.run_async(transport="stdio", show_banner=False),
            name="foxmcp-stdio"
        )
        websocket_task = asyncio.create_task(
            self.websocket_server.wait_closed(),
            name="foxmcp-websocket"
        )

        try:
            done, _ = await asyncio.wait(
                {mcp_task, websocket_task},
                return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for task in (mcp_task, websocket_task):
                task.cancel()

            # Awaited, not just cancelled: _stop_websocket_server() below waits
            # for the port to be released, and a live stdio task still holding
            # the connection open would make that wait pointless.
            await asyncio.gather(mcp_task, websocket_task, return_exceptions=True)
            await self._stop()

        # A tool that raised inside the transport is the client's problem to see,
        # so it is re-raised rather than logged as a clean shutdown.
        for task in done:
            if not task.cancelled() and task.exception() is not None:
                raise task.exception()

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
    parser.add_argument('--stdio', action='store_true',
                        help='Serve MCP over stdin/stdout instead of HTTP, so an MCP '
                             'client can launch the server itself. The WebSocket port '
                             'for the extension is unchanged.')
    parser.add_argument('--single-instance', action='store_true',
                        help='With --stdio, automatically start or join one shared browser '
                             'server for all chats using this WebSocket port.')
    parser.add_argument('--single-instance-idle-timeout', type=float, default=60.0,
                        metavar='SECONDS',
                        help='Stop the shared server after this long without clients '
                             '(default: 60 seconds; requires --single-instance).')
    parser.add_argument('--single-instance-worker', action='store_true',
                        help=argparse.SUPPRESS)
    parser.add_argument('--disable-tools', default=None, metavar='GROUP[,GROUP...]',
                        help='Comma-separated tool groups to leave unregistered, so their '
                             'descriptions never reach the client. Groups: '
                             f"{', '.join(sorted(FoxMCPTools.TOOL_GROUPS))}. "
                             'Overrides FOXMCP_DISABLE_TOOLS.')
    parser.add_argument('--enable-tools', default=None, metavar='TOOL[,TOOL...]',
                        help='Comma-separated individual tools to register even though '
                             'their group is disabled, named as the client sees them '
                             '(e.g. tabs_capture_screenshot). Overrides FOXMCP_ENABLE_TOOLS.')

    args = parser.parse_args()

    if args.single_instance and not args.stdio:
        parser.error('--single-instance requires --stdio')
    if args.single_instance_worker and not args.single_instance:
        parser.error('--single-instance-worker requires --stdio --single-instance')
    if (not args.single_instance and args.single_instance_idle_timeout != 60.0):
        parser.error('--single-instance-idle-timeout requires --single-instance')
    if not 0 < args.single_instance_idle_timeout < float('inf'):
        parser.error('--single-instance-idle-timeout must be a positive finite number')

    # Both of these are silent no-ops rather than errors if left to run, and a
    # user who typed them meant something by them. --no-mcp with --stdio asks for
    # a server with nothing on its stdout, which no client can use; --mcp-port
    # names a listener stdio mode does not open.
    if args.stdio and args.no_mcp:
        parser.error('--stdio and --no-mcp cannot be combined: stdio mode exists to '
                     'serve MCP, and --no-mcp turns it off')
    if args.stdio and args.mcp_port is not None:
        parser.error('--mcp-port has no meaning with --stdio: stdio mode serves MCP on '
                     'stdin/stdout and opens no HTTP listener')

    # FOXMCP_DISABLE_TOOLS is the same setting for a client that launches the server
    # through a wrapper: an MCP client config names the command and sets the
    # environment, but the arguments in between are often not the user's to edit.
    group_list = args.disable_tools
    if group_list is None:
        group_list = os.environ.get('FOXMCP_DISABLE_TOOLS', '')
    disabled_tool_groups = [g.strip() for g in group_list.split(',') if g.strip()]

    tool_list = args.enable_tools
    if tool_list is None:
        tool_list = os.environ.get('FOXMCP_ENABLE_TOOLS', '')
    enabled_tools = [t.strip() for t in tool_list.split(',') if t.strip()]

    # FoxMCPTools validates these again in its constructor, which is what enforces
    # the rule; checking here is what turns the ValueError into argparse's usage
    # message, so a mistyped group name reads as a command-line error rather than a
    # traceback from server startup.
    try:
        FoxMCPTools._validate_groups(disabled_tool_groups)
    except ValueError as e:
        parser.error(str(e))

    # Ensure localhost-only binding for security
    if args.host != 'localhost' and args.host != '127.0.0.1':
        logger.warning(f"Host '{args.host}' changed to 'localhost' for security")
        args.host = 'localhost'

    # --enable-tools is checked here rather than beside --disable-tools above,
    # because the tool names only exist once the tool definitions have run, which
    # happens inside this constructor. Turning its ValueError into argparse's
    # usage message keeps a mistyped tool name reading as a command-line error
    # rather than a traceback from server startup, the same as a mistyped group.
    try:
        server = FoxMCPServer(
            host=args.host,
            port=args.port,
            mcp_port=args.mcp_port,
            start_mcp=not args.no_mcp,
            disabled_tool_groups=disabled_tool_groups,
            enabled_tools=enabled_tools,
            use_stdio=args.stdio
        )
    except ValueError as e:
        parser.error(str(e))
    if args.single_instance:
        try:
            from .single_instance import run_proxy, run_worker
        except ImportError:
            from single_instance import run_proxy, run_worker
        if args.single_instance_worker:
            server.start_mcp = False
            await run_worker(server, args.single_instance_idle_timeout)
        else:
            await run_proxy(server, args.single_instance_idle_timeout)
        return
    await server.start_server()

def run() -> None:
    """Run the server with consistent exit codes for scripts and console entry points."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        # A server that could not start is a failure, and exiting 0 told every
        # caller otherwise. It matters most under --stdio: the client that
        # launched the process reports what it exited with, and often shows
        # nothing else.
        sys.exit(1)


if __name__ == "__main__":
    run()
