"""An automatically started, per-user browser server shared by stdio clients."""

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import uvicorn
import websockets
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server import create_proxy
from starlette.routing import WebSocketRoute


logger = logging.getLogger(__name__)
PROTOCOL = "foxmcp-single-instance-v1"
START_TIMEOUT = 30.0


def runtime_directory():
    """Keep the discovery token in the current user's private application data."""
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_RUNTIME_DIR", Path.home() / ".cache"))
    directory = root / "foxmcp"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


class InstanceLock:
    """An OS lock, released even when the owner crashes. Never delete this file."""

    def __init__(self, path):
        self.file = open(path, "a+b")
        self.locked = False

    def acquire(self):
        try:
            if os.name == "nt":
                import msvcrt

                if os.fstat(self.file.fileno()).st_size == 0:
                    self.file.write(b"\0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            return False
        self.locked = True
        return True

    def close(self):
        if self.locked:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()


def configuration_id(server):
    """Refuse to silently join a different checkout, version or tool setup."""
    directory = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in ("server.py", "mcp_tools.py", "file_transfer.py", "single_instance.py"):
        digest.update((directory / name).read_bytes())
    scripts = os.environ.get("FOXMCP_EXT_SCRIPTS")
    settings = {
        "source": str(directory),
        "code": digest.hexdigest(),
        "disabled": sorted(server.mcp_tools.disabled_groups),
        "enabled": sorted(server.mcp_tools.enabled_tools),
        "scripts": os.path.abspath(scripts) if scripts else None,
    }
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()


class PrivateEndpoint:
    """Protect both the internal MCP endpoint and its client lifetime channel."""

    def __init__(self, app, token, leases):
        self.app = app
        self.authorization = f"Bearer {token}".encode()
        self.leases = leases

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope["headers"])
            if (b"origin" in headers or not secrets.compare_digest(
                    headers.get(b"authorization", b""), self.authorization)):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await send({"type": "http.response.start", "status": 403, "headers": []})
                    await send({"type": "http.response.body", "body": b"Forbidden"})
                return
            if scope["type"] == "http":
                lease_id = headers.get(b"x-foxmcp-lease", b"").decode("ascii", errors="replace")
                sessions = self.leases.sessions.get(lease_id)
                if sessions is None:
                    await send({"type": "http.response.start", "status": 403, "headers": []})
                    await send({"type": "http.response.body", "body": b"Client disconnected"})
                    return

                async def record_session(message):
                    if message["type"] == "http.response.start":
                        session_id = dict(message.get("headers", [])).get(b"mcp-session-id")
                        if session_id:
                            sessions.add(session_id.decode("ascii"))
                    await send(message)

                await self.app(scope, receive, record_session)
                return
        await self.app(scope, receive, send)


class ClientLeases:
    """A live socket is a lease; a crashed client releases it without a heartbeat."""

    def __init__(self, configuration, server):
        self.configuration = configuration
        self.server = server
        self.active = set()
        self.sessions = {}
        self.last_departure = time.monotonic()
        self.stopping = False

    async def connect(self, websocket):
        if self.stopping:
            await websocket.close(code=1013)
            return
        await websocket.accept()
        self.active.add(websocket)
        lease_id = secrets.token_urlsafe(32)
        self.sessions[lease_id] = set()
        try:
            await websocket.send_json({"protocol": PROTOCOL,
                                       "configuration": self.configuration,
                                       "pid": os.getpid(), "lease": lease_id})
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
        finally:
            self.active.discard(websocket)
            self.last_departure = time.monotonic()
            sessions = self.sessions.pop(lease_id)
            # A killed proxy cannot send MCP's DELETE. Its lease still closes,
            # so terminate its sessions and let the existing monitor reaper work.
            for route in self.server.mcp_http_app.routes:
                manager = getattr(getattr(route, "app", None), "session_manager", None)
                transports = getattr(manager, "_server_instances", {})
                for session_id in sessions:
                    transport = transports.get(session_id)
                    if transport is not None:
                        await transport.terminate()

    async def wait_until_idle(self, timeout):
        while True:
            await asyncio.sleep(min(timeout, 1.0))
            if not self.active and time.monotonic() - self.last_departure >= timeout:
                # Set before yielding so a new lease cannot race shutdown.
                self.stopping = True
                return


async def run_worker(server, idle_timeout):
    """Own the browser port independently of any particular chat's process."""
    directory = runtime_directory()
    metadata_path = directory / f"instance-{server.port}.json"
    lock = InstanceLock(directory / f"instance-{server.port}.lock")
    if not lock.acquire():
        lock.close()
        return  # Another contender won the startup race.

    tasks = []
    http_server = None
    listener = None
    temporary = None
    try:
        # A previous owner may have been killed without removing its discovery file.
        metadata_path.unlink(missing_ok=True)
        token = secrets.token_urlsafe(32)
        leases = ClientLeases(configuration_id(server), server)
        server.mcp_http_app = server.mcp_app.http_app()
        server.mcp_http_app.routes.append(WebSocketRoute("/instance", leases.connect))

        # The kernel chooses and reserves the internal port; port 3000 is untouched.
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        http_server = uvicorn.Server(uvicorn.Config(
            PrivateEndpoint(server.mcp_http_app, token, leases), host="127.0.0.1",
            log_level="warning", access_log=False, timeout_graceful_shutdown=5,
        ))
        browser_task = asyncio.create_task(server.start_server())
        http_task = asyncio.create_task(http_server.serve(sockets=[listener]))
        tasks.extend((browser_task, http_task))
        while server.websocket_server is None or not http_server.started:
            for task in tasks:
                if task.done():
                    await task
                    raise RuntimeError("Shared server stopped during startup")
            await asyncio.sleep(0.05)

        server.monitor_reaper_task = asyncio.create_task(server._reap_monitors())
        metadata = {"protocol": PROTOCOL, "port": listener.getsockname()[1],
                    "token": token, "pid": os.getpid()}
        temporary = metadata_path.with_suffix(f".{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as file:
            json.dump(metadata, file)
        os.replace(temporary, metadata_path)
        logger.info("Shared server ready (PID %s, browser port %s)", os.getpid(), server.port)
        idle_task = asyncio.create_task(leases.wait_until_idle(idle_timeout))
        tasks.append(idle_task)
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    finally:
        metadata_path.unlink(missing_ok=True)
        if temporary:
            temporary.unlink(missing_ok=True)
        if http_server:
            http_server.should_exit = True
            # Let uvicorn close its listener and ASGI lifespan before cancelling
            # tasks, including when the browser port failed during startup.
            if len(tasks) >= 2 and not tasks[1].done():
                try:
                    await asyncio.wait_for(asyncio.shield(tasks[1]), 8)
                except Exception:
                    logger.debug("Internal HTTP server did not shut down cleanly", exc_info=True)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await server._stop()
        if listener:
            listener.close()
        lock.close()


def spawn_worker(server, idle_timeout, log_path):
    command = [sys.executable, str(Path(__file__).with_name("server.py")),
               "--stdio", "--single-instance", "--single-instance-worker",
               "--host", server.host, "--port", str(server.port),
               "--single-instance-idle-timeout", str(idle_timeout),
               "--disable-tools", ",".join(sorted(server.mcp_tools.disabled_groups)),
               "--enable-tools", ",".join(sorted(server.mcp_tools.enabled_tools))]
    options = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    }
    with open(log_path, "ab") as log:
        return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=log, close_fds=True, **options)


async def discover(server, idle_timeout):
    directory = runtime_directory()
    metadata_path = directory / f"instance-{server.port}.json"
    log_path = directory / f"instance-{server.port}.log"
    deadline = time.monotonic() + START_TIMEOUT
    worker = None
    last_error = None
    while time.monotonic() < deadline:
        lease = None
        try:
            metadata = json.loads(metadata_path.read_text())
            if (metadata.get("protocol") != PROTOCOL
                    or type(metadata.get("port")) is not int
                    or not 0 < metadata["port"] < 65536
                    or not isinstance(metadata.get("token"), str)):
                raise ValueError("Invalid shared server discovery file")
            address = f"127.0.0.1:{metadata['port']}"
            headers = {"Authorization": f"Bearer {metadata['token']}"}
            lease = await websockets.connect(f"ws://{address}/instance",
                                             additional_headers=headers, open_timeout=1)
            hello = json.loads(await asyncio.wait_for(lease.recv(), 2))
            if hello.get("protocol") != PROTOCOL:
                raise ValueError("Unrecognized shared server")
            if hello.get("configuration") != configuration_id(server):
                await lease.close()
                raise RuntimeError(
                    "The shared FoxMCP server uses different code or tool/script settings. "
                    "Use matching settings, or close its clients and wait for idle shutdown."
                )
            logger.info("Using shared FoxMCP server (PID %s)", hello["pid"])
            headers["X-FoxMCP-Lease"] = hello["lease"]
            return lease, f"http://{address}/mcp", headers
        except (OSError, ValueError, websockets.WebSocketException, asyncio.TimeoutError) as error:
            last_error = error
            if lease:
                await lease.close()
        # A contender can lose to an owner that is just shutting down. Once
        # that contender exits, retry election instead of waiting forever for
        # an owner that has already gone.
        if worker is None or worker.poll() == 0:
            worker = spawn_worker(server, idle_timeout, log_path)
        elif worker.poll() not in (None, 0):
            raise RuntimeError(f"Shared FoxMCP server failed to start; see {log_path}")
        await asyncio.sleep(0.1)
    raise RuntimeError(f"Cannot reach the shared FoxMCP server: {last_error}; see {log_path}")


async def run_proxy(server, idle_timeout):
    lease, url, headers = await discover(server, idle_timeout)
    try:
        # One upstream MCP session per stdio process. Keeping it connected also
        # gives request monitors the same lifetime as the chat that owns them.
        async with Client(StreamableHttpTransport(url, headers=headers)) as client:
            proxy = create_proxy(client, name="FoxMCP")
            await proxy.run_async(transport="stdio", show_banner=False)
    finally:
        await lease.close()
