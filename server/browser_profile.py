"""State and request processing belonging to one Firefox connection."""

import asyncio
from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, Optional
import uuid

try:
    from .version import VERSION
except ImportError:
    from version import VERSION

logger = logging.getLogger(__name__)


class BrowserProfile:
    NO_MCP_SESSION = "no-mcp-session"
    MONITOR_LIFECYCLE_ACTIONS = ("requests.start_monitoring", "requests.stop_monitoring")

    def __init__(self, server, websocket, profile_id, origin):
        self.server = server
        self.profile_id = profile_id
        self.origin = origin
        self.connection_id = uuid.uuid4().hex
        self.extension_connection = websocket
        self.extension_version = None
        self.pending_requests = {}
        self.monitor_owners = {}
        self.monitors_being_stopped = set()
        self.browser_hub = server.browser_hub
        self._browser_loop = server._browser_loop

    @property
    def mcp_http_app(self):
        return self.server.mcp_http_app

    def disconnected(self):
        """Fail this socket's requests and release only its monitor ownership."""
        self.monitor_owners.clear()
        for future in list(self.pending_requests.values()):
            if not future.done():
                future.set_result({"error": "Browser extension disconnected", "profile_id": self.profile_id})

    async def handle_extension_message(self, message: str):
        """Process message from browser extension"""
        try:
            data = json.loads(message)
            if not isinstance(data, dict):
                return
            message_type = data.get('type', 'unknown')
            if message_type == 'hello':
                payload = data.get('data')
                version = payload.get('version') if isinstance(payload, dict) else None
                if (isinstance(version, str) and len(version) <= 64
                        and re.fullmatch(r'[0-9]+(?:\.[0-9]+){0,3}', version)):
                    if version != self.extension_version:
                        if version != VERSION:
                            logger.warning(
                                "FoxMCP version mismatch: extension %s, server %s. "
                                "Update extension and server together; browser tools remain available.",
                                version, VERSION
                            )
                        else:
                            logger.info("FoxMCP versions match: extension %s, server %s", version, VERSION)
                    self.extension_version = version
                return
            message_id = data.get('id')
            action = data.get('action', 'unknown')

            # Handle debug logs specially - print them prominently
            if message_type == 'debug_log':
                level = data.get('data', {}).get('level', 'log')
                log_message = data.get('data', {}).get('message', '')
                timestamp = data.get('data', {}).get('timestamp', '')

                logger.info("----- EXTENSION DEBUG LOG -----")
                if level == 'error':
                    logger.info(f"🔴 EXTENSION ERROR [{timestamp}]: {log_message}")
                else:
                    logger.info(f"🔵 EXTENSION LOG [{timestamp}]: {log_message}")
                return

            logger.info(f"Received from extension: {message_type} - {action} (ID: {message_id})")

            # The extension answered for a monitor the server has no record of,
            # so nothing can reach it: stop it rather than leave it capturing.
            #
            # The two sides can only drift this way if one of them let go of a
            # monitor the other kept - an extension too old to clear its monitors
            # when a connection ends, or a server that has forgotten an owner. In
            # a matched pair this never fires, which is why it is worth having: it
            # is the case nobody planned for.
            stray_monitor = self._stray_monitor_named_in(action, data)
            if stray_monitor:
                asyncio.create_task(self._stop_stray_monitor(stray_monitor))

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
            if not future.done():
                future.set_result({**response_data, "profile_id": self.profile_id, "connection_id": self.connection_id})
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
            # Routing belongs to the server; the extension only knows its socket.
            message = {key: value for key, value in message.items() if key != 'profile_id'}
            message['timestamp'] = datetime.now().isoformat()
            await self.extension_connection.send(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Error sending to extension: {e}")
            return False

    async def send_request_and_wait(self, request: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """Send request to extension and wait for response"""
        # HTTP MCP runs on uvicorn's thread. Browser sockets and their reply
        # futures must stay on the listener's loop, also when HTTP and stdio
        # clients share the same browser connection.
        if self._browser_loop is not None and asyncio.get_running_loop() is not self._browser_loop:
            result = asyncio.run_coroutine_threadsafe(
                self.send_request_and_wait(request, timeout), self._browser_loop
            )
            return await asyncio.wrap_future(result)
        request_id = request.get('id')
        if not request_id:
            raise ValueError("Request must have an ID")

        if not self.extension_connection:
            return {"error": "No extension connection available"}

        if request_id in self.pending_requests:
            return {"error": "Request ID is already in flight"}

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
        finally:
            self.pending_requests.pop(request_id, None)

    def register_monitor(self, monitor_id: str, session_id: str):
        """Record the MCP client a newly started request monitor belongs to

        Called by the requests_start_monitoring tool once the extension has
        answered with an id. Monitors with no owner recorded are never reaped;
        that is what happens when a tool is called outside an MCP session, as the
        test harness does.
        """
        if monitor_id:
            self.monitor_owners[monitor_id] = session_id or self.NO_MCP_SESSION

    def forget_monitor(self, monitor_id: str):
        """Drop a monitor the client stopped itself, so the reaper ignores it"""
        self.monitor_owners.pop(monitor_id, None)

    def _live_mcp_session_ids(self) -> Optional[set]:
        """Sessions of the MCP clients still connected, or None if that cannot be told

        None and the empty set mean different things: None is "no answer
        available" and must not be read as "every client has gone".

        `_server_instances` is private to the MCP SDK's
        StreamableHTTPSessionManager, and fastmcp reaches into it the same way in
        its own shutdown path. A terminated session stays in that dict rather than
        being removed, so `is_terminated` is what separates a client that has gone
        from one that is merely quiet.
        """
        app = self.mcp_http_app
        if app is None:
            return None

        for route in getattr(app, 'routes', []):
            manager = getattr(getattr(route, 'app', None), 'session_manager', None)
            transports = getattr(manager, '_server_instances', None)
            if transports is not None:
                return {
                    session_id
                    for session_id, transport in list(transports.items())
                    if not getattr(transport, 'is_terminated', False)
                }

        return None

    async def stop_monitors_of_gone_clients(self):
        """Stop every running monitor whose MCP client has disconnected

        A monitor outlives the client that started it: it lives in the extension,
        and only its creator ever knew its id. Left alone it keeps the extension's
        webRequest listeners registered and filters response bodies nobody can
        read.

        A monitor whose extension has gone is forgotten here rather than stopped:
        the extension clears its own monitors whenever a connection ends, so there
        is nothing left to stop.
        """
        if not self.monitor_owners:
            return

        live_sessions = self._live_mcp_session_ids()
        proxy_sessions = set(self.browser_hub.clients.values())
        abandoned = [
            monitor_id for monitor_id, session_id in self.monitor_owners.items()
            if (session_id.startswith('proxy:') and session_id not in proxy_sessions)
            or (not session_id.startswith('proxy:') and live_sessions is not None
                and session_id != self.NO_MCP_SESSION and session_id not in live_sessions)
        ]

        for monitor_id in abandoned:
            self.monitor_owners.pop(monitor_id, None)

            if not self.extension_connection:
                continue

            request = {
                "id": f"reap_{monitor_id}",
                "type": "request",
                "action": "requests.stop_monitoring",
                "data": {"monitor_id": monitor_id},
                "timestamp": datetime.now().isoformat()
            }
            response = await self.send_request_and_wait(request, timeout=10.0)
            if "error" in response or response.get("type") == "error":
                detail = response.get("error") or response.get("data", {}).get("message", response)
                logger.warning(f"Could not stop monitor {monitor_id} of a departed MCP client: {detail}")
            else:
                logger.info(f"Stopped monitor {monitor_id}: the MCP client that started it has gone")

    def _stray_monitor_named_in(self, action: str, message: Dict[str, Any]) -> Optional[str]:
        """The monitor id in a message from the extension that no client owns, if any

        Returns None for the monitor lifecycle replies, which name ids the registry
        is not expected to hold yet or any more.
        """
        if action in self.MONITOR_LIFECYCLE_ACTIONS:
            return None

        payload = message.get('data')
        if not isinstance(payload, dict):
            return None

        monitor_id = payload.get('monitor_id')
        if not monitor_id or monitor_id in self.monitor_owners:
            return None

        return monitor_id

    async def _stop_stray_monitor(self, monitor_id: str):
        """Stop a monitor the extension is running that no client can reach

        Runs as its own task so the message being handled is not held up waiting
        for the extension to answer this.
        """
        if monitor_id in self.monitors_being_stopped:
            return

        self.monitors_being_stopped.add(monitor_id)
        try:
            request = {
                "id": f"stray_{monitor_id}",
                "type": "request",
                "action": "requests.stop_monitoring",
                "data": {"monitor_id": monitor_id},
                "timestamp": datetime.now().isoformat()
            }
            response = await self.send_request_and_wait(request, timeout=10.0)
            if "error" in response or response.get("type") == "error":
                detail = response.get("error") or response.get("data", {}).get("message", response)
                logger.warning(f"Could not stop stray monitor {monitor_id}: {detail}")
            else:
                logger.info(f"Stopped stray monitor {monitor_id}: no MCP client owns it")
        finally:
            self.monitors_being_stopped.discard(monitor_id)
