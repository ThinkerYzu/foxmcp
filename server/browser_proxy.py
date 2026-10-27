"""Discovery and browser-command forwarding on the extension's existing port."""

import asyncio
from http import HTTPStatus
import ipaddress
import json
import logging
import math
import os
import re
import time
import uuid

from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)
SERVER_NAME = "FoxMCP"
PROTOCOL_VERSION = 3
EXTENSION_ORIGIN_PATTERN = re.compile(r"moz-extension://.+")


class BrowserProxyHub:
    """Route extension and local-client sockets without mixing their identities."""

    def __init__(self, server):
        self.server = server
        self.clients = {}
        self.idle_timeout = None  # Manually started servers have no idle shutdown.
        self.last_departure = time.monotonic()
        self.stopping = False

    @staticmethod
    def _is_local_host(authority):
        # Validate the authority independently of the listener port: a local
        # TCP forwarder preserves Host while connecting to a different port.
        match = re.fullmatch(
            r"(?:localhost|127\.0\.0\.1|\[::1\])(?::([0-9]{1,5}))?",
            authority.lower(),
        )
        return match is not None and (
            match[1] is None or 1 <= int(match[1]) <= 65535
        )

    def discovery(self):
        return {
            "server": SERVER_NAME,
            "protocol_version": PROTOCOL_VERSION,
            "proxy_path": "/proxy",
            "pid": os.getpid(),
            "lifetime": "automatic" if self.idle_timeout is not None else "manual",
        }

    def process_request(self, connection, request):
        """Apply route-specific access checks before a socket can replace Firefox."""
        host = request.headers.get_all("Host")
        origin = request.headers.get_all("Origin")
        remote = ipaddress.ip_address(connection.remote_address[0])
        if not remote.is_loopback or len(host) != 1 or not self._is_local_host(host[0]):
            return connection.respond(HTTPStatus.FORBIDDEN, "Localhost clients only\n")

        if request.path == "/":
            if not request.headers.get_all("Upgrade"):
                return connection.respond(
                    HTTPStatus.UPGRADE_REQUIRED, "WebSocket required\n"
                )
            if len(origin) != 1 or not EXTENSION_ORIGIN_PATTERN.fullmatch(origin[0]):
                return connection.respond(
                    HTTPStatus.FORBIDDEN, "Extension origin required\n"
                )
        elif request.path in ("/discovery", "/proxy"):
            # Browser scripts always send Origin on WebSockets. Discovery has
            # no CORS allowance either; reject even simple HTTP page requests.
            if origin:
                return connection.respond(
                    HTTPStatus.FORBIDDEN, "Browser origins are refused\n"
                )
            if self.stopping:
                return connection.respond(
                    HTTPStatus.SERVICE_UNAVAILABLE, "Server stopping\n"
                )
            if request.path == "/discovery":
                response = connection.respond(
                    HTTPStatus.OK, json.dumps(self.discovery())
                )
                del response.headers["Content-Type"]
                response.headers["Content-Type"] = "application/json"
                response.headers["Cache-Control"] = "no-store"
                return response
        else:
            return connection.respond(HTTPStatus.NOT_FOUND, "Unknown endpoint\n")
        return None

    async def handle_connection(self, websocket):
        if websocket.request.path == "/proxy":
            await self.handle_proxy(websocket)
        else:
            await self.server.handle_extension_connection(websocket)

    async def handle_proxy(self, websocket):
        owner = f"proxy:{uuid.uuid4().hex}"
        self.clients[websocket] = owner
        pending = {}
        try:
            await websocket.send(json.dumps({"type": "hello", **self.discovery()}))
            async for message in websocket:
                try:
                    request = json.loads(message)
                    if not isinstance(request, dict):
                        raise ValueError("Request must be an object")
                    request_id = request.get("id")
                    timeout = request.get("timeout", 30.0)
                    if (
                        not isinstance(request_id, str)
                        or not request_id
                        or request.get("type") != "request"
                        or not isinstance(request.get("action"), str)
                        or not isinstance(request.get("data", {}), dict)
                        or not isinstance(timeout, (float, int))
                        or isinstance(timeout, bool)
                        or not 0 < timeout <= 300
                        or not math.isfinite(timeout)
                    ):
                        raise ValueError("Invalid browser request")
                    if request_id in pending:
                        raise ValueError("Request ID is already in flight")
                except (ValueError, TypeError):
                    await websocket.close(code=1008, reason="Invalid browser request")
                    break
                task = asyncio.create_task(
                    self.forward(websocket, owner, request, timeout)
                )
                pending[request_id] = task
                task.add_done_callback(
                    lambda _task, key=request_id: pending.pop(key, None)
                )
        except ConnectionClosed:
            pass
        finally:
            # A start-monitoring call may finish after the client goes away.
            # Finish tracking its reply before cleaning up everything it owned.
            await asyncio.gather(*list(pending.values()), return_exceptions=True)
            self.clients.pop(websocket, None)
            try:
                await self.server.stop_monitors_of_gone_clients()
            finally:
                self.last_departure = time.monotonic()

    async def forward(self, websocket, owner, request, timeout):
        original_id = request["id"]
        action = request["action"]
        try:
            if action == "proxy.status":
                response = {
                    "type": "response",
                    "action": action,
                    "data": {"status": await self.server.get_extension_status()},
                }
            elif action == "proxy.profiles":
                response = {"type": "response", "action": action,
                            "data": await self.server.list_profiles(
                                populate=request.get("data", {}).get("populate", True))}
            else:
                upstream = {**request, "id": uuid.uuid4().hex}
                upstream.pop("timeout", None)
                response = await self.server.send_request_and_wait(
                    upstream, timeout=timeout
                )
                if response.get("type") == "response":
                    data = response.get("data", {})
                    if action == "requests.start_monitoring":
                        self.server.register_monitor(request.get("profile_id"), data.get("monitor_id"), owner, response.get("connection_id"))
                    elif action == "requests.stop_monitoring":
                        self.server.forget_monitor(
                            request.get("profile_id"), request.get("data", {}).get("monitor_id"), response.get("connection_id")
                        )
            await websocket.send(json.dumps({**response, "id": original_id}))
        except ConnectionClosed:
            pass
        except Exception:
            logger.exception("Browser proxy request failed: %s", action)
            try:
                await websocket.send(
                    json.dumps(
                        {"id": original_id, "error": "Browser proxy request failed"}
                    )
                )
            except ConnectionClosed:
                pass

    async def wait_until_idle(self):
        while True:
            await asyncio.sleep(min(self.idle_timeout, 1.0))
            if (
                not self.clients
                and time.monotonic() - self.last_departure >= self.idle_timeout
            ):
                self.stopping = True
                return


class RemoteBrowser:
    """The browser interface used by local MCP tools, over a shared proxy socket."""

    def __init__(self, websocket, file_transfers):
        self.websocket = websocket
        self.file_transfers = file_transfers
        self.pending = {}
        self.reader = asyncio.create_task(self.read_responses())

    async def read_responses(self):
        try:
            async for message in self.websocket:
                response = json.loads(message)
                future = self.pending.get(response.get("id"))
                if future is not None and not future.done():
                    future.set_result(response)
        except (ConnectionClosed, ValueError, TypeError, AttributeError):
            pass
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_result(
                        {
                            "error": "Browser proxy disconnected; reconnect the MCP client"
                        }
                    )

    async def send_request_and_wait(self, request, timeout=30.0):
        if self.reader.done():
            return {"error": "Browser proxy disconnected; reconnect the MCP client"}
        request_id = request["id"]
        if request_id in self.pending:
            return {"error": "Request ID is already in flight"}
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.websocket.send(json.dumps({**request, "timeout": timeout}))
            return await asyncio.wait_for(future, timeout + 1)
        except ConnectionClosed:
            return {"error": "Browser proxy disconnected; reconnect the MCP client"}
        except asyncio.TimeoutError:
            return {"error": f"Request timed out after {timeout} seconds"}
        finally:
            self.pending.pop(request_id, None)

    async def list_profiles(self, populate=True):
        response = await self.send_request_and_wait({
            "id": uuid.uuid4().hex, "type": "request", "action": "proxy.profiles",
            "data": {"populate": populate}}, timeout=10.0)
        if "error" in response:
            return {"profiles": [], "error": response["error"]}
        return response.get("data", {"profiles": [], "error": "Invalid profile discovery response"})

    async def get_extension_status(self):
        response = await self.send_request_and_wait(
            {
                "id": uuid.uuid4().hex,
                "type": "request",
                "action": "proxy.status",
                "data": {},
            }
        )
        return response.get("data", {}).get("status") or response.get(
            "error", "Unknown browser status"
        )

    async def close(self):
        await self.websocket.close()
        await self.reader
