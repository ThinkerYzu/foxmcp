"""Browser ownership: listener, profile registry, routing and monitor cleanup."""

import asyncio
from collections import Counter
from datetime import datetime
import json
import logging
import os
from typing import Any, Dict
import uuid

import websockets

try:
    from .version import VERSION
    from .browser_proxy import BrowserProxyHub, EXTENSION_ORIGIN_PATTERN, PROTOCOL_VERSION
    from .browser_profile import BrowserProfile
    from .profile_names import FirefoxProfileNames
except ImportError:
    from version import VERSION
    from browser_proxy import BrowserProxyHub, EXTENSION_ORIGIN_PATTERN, PROTOCOL_VERSION
    from browser_profile import BrowserProfile
    from profile_names import FirefoxProfileNames

logger = logging.getLogger(__name__)


class BrowserServer:
    """Own Firefox connections independently of any MCP transport."""

    MONITOR_REAP_INTERVAL = 5.0

    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.profiles = {}
        self._next_profile_id = 1
        self.profile_names = FirefoxProfileNames()
        self._connection_waiters = []
        self.websocket_server = None
        self._browser_loop = None
        self.proxy_hub = BrowserProxyHub(self)
        self.monitor_reaper_task = None
        # HTTP composition supplies a session provider. None means unknown,
        # never "all clients departed". BrowserProfile knows no FastMCP internals.
        self.live_mcp_session_ids = lambda: None

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


    async def start_browser_listener(self):
        """Bind the common discovery, proxy and extension port atomically."""
        self._browser_loop = asyncio.get_running_loop()
        try:
            self.websocket_server = await websockets.serve(
                self.proxy_hub.handle_connection,
                self.host,
                self.port,
                # Windows SO_REUSEADDR permits stealing an occupied listening
                # port; Unix needs it to reuse a port after a clean shutdown.
                reuse_address=os.name != 'nt',
                # Rejected during the handshake, so a non-extension client never
                # reaches handle_extension_connection - which validates and registers
                # a separate BrowserProfile for each accepted connection.
                origins=[EXTENSION_ORIGIN_PATTERN, None],
                process_request=self.proxy_hub.process_request,
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


    async def stop_monitor_reaper(self):
        """Stop polling before MCP transports and browser sockets are closed."""
        if self.monitor_reaper_task:
            self.monitor_reaper_task.cancel()
            try:
                await self.monitor_reaper_task
            except asyncio.CancelledError:
                pass
            self.monitor_reaper_task = None

    async def _stop(self):
        """Release browser-owned tasks and listening sockets."""
        await self.stop_monitor_reaper()
        await self._stop_websocket_server()

    async def start_server(self):
        """Run the browser-only server; MCP composition lives in server.py."""
        try:
            await self.start_browser_listener()
            await self.websocket_server.wait_closed()
        finally:
            await self._stop()
