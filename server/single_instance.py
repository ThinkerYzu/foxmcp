"""Automatically start or join a browser server on the extension port."""

import asyncio
import errno
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
import websockets

try:
    from .browser_proxy import RemoteBrowser, SERVER_NAME, PROTOCOL_VERSION
except ImportError:
    from browser_proxy import RemoteBrowser, SERVER_NAME, PROTOCOL_VERSION


logger = logging.getLogger(__name__)
START_TIMEOUT = 30.0


def runtime_directory():
    """Per-user log directory; no discovery metadata or locks are stored."""
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_RUNTIME_DIR", Path.home() / ".cache"))
    directory = root / "foxmcp"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


async def run_worker(server, idle_timeout):
    """Let the listening socket arbitrate election between detached contenders."""
    server.browser_hub.idle_timeout = idle_timeout
    tasks = []
    try:
        try:
            await server.start_browser_listener()
        except OSError as error:
            if error.errno == errno.EADDRINUSE or getattr(error, "winerror", None) == 10048:
                return
            raise
        tasks = [asyncio.create_task(server.browser_hub.wait_until_idle()),
                 asyncio.create_task(server.websocket_server.wait_closed())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await server._stop()


def spawn_worker(server, idle_timeout, log_path):
    command = [sys.executable, str(Path(__file__).with_name("server.py")),
               "--stdio", "--single-instance", "--single-instance-worker",
               "--host", server.host, "--port", str(server.port),
               "--single-instance-idle-timeout", str(idle_timeout),
               "--disable-tools", ",".join(sorted(server.mcp_tools.disabled_groups)),
               "--enable-tools", ",".join(sorted(server.mcp_tools.enabled_tools))]
    if os.name == "nt":
        return spawn_windows_worker(command, log_path)
    with open(log_path, "ab") as log:
        return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=log, close_fds=True, start_new_session=True)


def spawn_windows_worker(command, log_path):
    """Let WMI own the worker outside the MCP client's Windows Job Object.

    DETACHED_PROCESS only detaches a console: the worker still inherits the
    client's kill-on-close job. The local WMI provider launches independently.
    A small PowerShell broker waits for its exit so discovery can still detect
    startup failures. Killing that broker does not kill the shared worker.
    """
    bootstrap = (
        "import os,runpy,sys; "
        "sys.stdin=open(os.devnull); sys.stdout=open(os.devnull,'w'); "
        "sys.stderr=open(sys.argv[1],'a',encoding='utf-8'); "
        "sys.argv=sys.argv[2:]; sys.path.insert(0,os.path.dirname(sys.argv[0])); "
        "runpy.run_path(sys.argv[0],run_name='__main__')"
    )
    payload = {
        "command": subprocess.list2cmdline(
            [command[0], "-c", bootstrap, str(log_path), *command[1:]]),
        "cwd": os.getcwd(),
        "environment": [f"{name}={value}" for name, value in os.environ.items()],
    }
    # Data goes over stdin, never interpolated into PowerShell or exposed in its
    # command line. Preserve the caller's environment, including script settings.
    script = r"""$ErrorActionPreference = 'Stop'
$settings = [Console]::In.ReadToEnd() | ConvertFrom-Json
$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{
    ShowWindow = [uint16]0
    # CREATE_NO_WINDOW (0x08000000) keeps the virtualenv Python child hidden too.
    # ShowWindow didn't prevent that child from opening a console.
    # Replaces DETACHED_PROCESS (0x8): combining it with CREATE_NO_WINDOW disables the latter.
    # Keep BREAKAWAY_FROM_JOB (0x01000000), NEW_PROCESS_GROUP (0x200), and UNICODE_ENVIRONMENT (0x400)
    # so worker lifetime and environment stay intact.
    CreateFlags = [uint32]0x09000600
    EnvironmentVariables = [string[]]$settings.environment
}
$created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = [string]$settings.command
    CurrentDirectory = [string]$settings.cwd
    ProcessStartupInformation = $startup
}
if ($created.ReturnValue -ne 0) {
    throw "Cannot start shared FoxMCP server: WMI error $($created.ReturnValue)"
}
$worker = [Diagnostics.Process]::GetProcessById($created.ProcessId)
$worker.WaitForExit()
exit $worker.ExitCode
"""
    with open(log_path, "ab") as log:
        broker = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True,
        )
    try:
        broker.stdin.write(json.dumps(payload).encode("ascii"))
    finally:
        broker.stdin.close()
    return broker


class IncompatibleServer(RuntimeError):
    """The configured port belongs to a server that cannot forward our requests."""


async def probe(host, port):
    """Read only the configured loopback port; never follow discovery redirects."""
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(f"http://{host}:{port}/discovery", timeout=1.0)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        return None
    if response.status_code == 503:
        return None  # A compatible owner can be between idle shutdown and unbind.
    try:
        metadata = response.json()
        compatible = (response.status_code == 200 and isinstance(metadata, dict)
                      and metadata.get("server") == SERVER_NAME
                      and type(metadata.get("protocol_version")) is int
                      and metadata["protocol_version"] == PROTOCOL_VERSION
                      and metadata.get("proxy_path") == "/proxy")
    except ValueError:
        compatible = False
    if not compatible:
        raise IncompatibleServer(
            f"Port {port} is occupied by an incompatible server; "
            "restart FoxMCP with a version supporting /discovery and /proxy"
        )
    return metadata


async def discover(server, idle_timeout):
    """Join an owner or start a contender; a failed bind retries discovery."""
    log_path = None
    deadline = time.monotonic() + START_TIMEOUT
    worker = None
    while time.monotonic() < deadline:
        metadata = await probe(server.host, server.port)
        if metadata is not None:
            connection = None
            try:
                connection = await websockets.connect(
                    f"ws://{server.host}:{server.port}/proxy", open_timeout=2,
                    max_size=None, proxy=None,
                )
                hello = json.loads(await asyncio.wait_for(connection.recv(), 2))
                if (not isinstance(hello, dict) or hello.get("type") != "hello"
                        or hello.get("server") != SERVER_NAME
                        or hello.get("protocol_version") != PROTOCOL_VERSION):
                    raise IncompatibleServer("Incompatible FoxMCP forwarding protocol")
                logger.info("Using shared FoxMCP server (PID %s)", hello.get("pid"))
                return connection
            except (OSError, websockets.WebSocketException, asyncio.TimeoutError):
                if connection:
                    await connection.close()
            except Exception:
                if connection:
                    await connection.close()
                raise
        elif worker is None or worker.poll() == 0:
            if log_path is None:
                log_path = runtime_directory() / f"instance-{server.port}.log"
            worker = spawn_worker(server, idle_timeout, log_path)
        elif worker.poll() is not None:
            raise RuntimeError(f"Shared FoxMCP server failed to start; see {log_path}")
        await asyncio.sleep(0.1)
    detail = f"; see {log_path}" if log_path is not None else ""
    raise RuntimeError(f"Cannot reach FoxMCP on {server.host}:{server.port}{detail}")


async def run_proxy(server, idle_timeout):
    websocket = await discover(server, idle_timeout)
    browser = RemoteBrowser(websocket, server.file_transfers)
    # Tool definitions and script execution stay in this stdio process. Only
    # browser requests cross the socket, so each chat keeps its own settings.
    server.mcp_tools.websocket_server = browser
    try:
        await server.mcp_app.run_async(transport="stdio", show_banner=False)
    finally:
        await browser.close()
        await asyncio.to_thread(server.file_transfers.close)
