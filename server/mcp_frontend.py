"""MCP-facing transport, tools, scripts and local-file transfers."""

import asyncio
import logging
import os
import socket
import sys
import threading
from typing import Protocol

import uvicorn

try:
    from .file_transfer import FileTransferServer
    from .mcp_tools import FoxMCPTools
except ImportError:
    from file_transfer import FileTransferServer
    from mcp_tools import FoxMCPTools

logger = logging.getLogger(__name__)


class Browser(Protocol):
    """The same browser access contract for BrowserServer and RemoteBrowser."""

    async def send_request_and_wait(self, request: dict, timeout: float = 30.0) -> dict: ...
    async def list_profiles(self, populate: bool = True) -> dict: ...
    async def get_extension_status(self) -> str: ...
    def register_monitor(self, profile_id, monitor_id, session_id, connection_id) -> None: ...
    def forget_monitor(self, profile_id, monitor_id, connection_id) -> None: ...


# Try to import port coordinator for dynamic port allocation
try:
    tests_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')
    sys.path.insert(0, tests_dir)
    from port_coordinator import get_port_by_type
    HAS_PORT_COORDINATOR = True
except ImportError:
    HAS_PORT_COORDINATOR = False


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

class MCPFrontend:
    """Serve an MCP client using an injected local or remote browser."""

    def __init__(self, browser: Browser, host="localhost", port=None,
                 use_stdio=False, disabled_tool_groups=None, enabled_tools=None):
        self.browser = browser
        self.host = host
        self.use_stdio = use_stdio
        # In stdio mode the MCP side has no listener, so there is no port to pick.
        # Running the selection anyway would bind-test a port nothing serves and
        # report "port in use" against whatever else holds 3000 - most likely the
        # user's own HTTP-mode server, which is not a conflict at all here.
        if self.use_stdio:
            self.port = None
        # Set MCP port - default to 3000 for production, dynamic allocation only for tests
        elif port is None:
            # Check if we're in a test environment by checking for pytest or explicit test indicators
            in_test_env = ('pytest' in sys.modules or
                          'PYTEST_CURRENT_TEST' in os.environ or
                          any('pytest' in path or 'test_' in os.path.basename(path) for path in sys.path))
            if in_test_env and HAS_PORT_COORDINATOR:
                # Use dynamic port allocation for tests to avoid conflicts
                self.port = find_available_port(3000)
            else:
                # Use fixed port 3000 for production
                self.port = 3000
        else:
            # Check if requested port is available
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(('localhost', port))
                    self.port = port
            except OSError:
                logger.warning(f"Requested MCP port {port} is in use, finding alternative...")
                self.port = find_available_port(port)

        if self.port is not None:
            logger.info(f"MCP server will use port {self.port}")
        self.file_transfers = FileTransferServer()
        self.tools = FoxMCPTools(browser, disabled_groups=disabled_tool_groups,
                                 enabled_tools=enabled_tools, file_transfers=self.file_transfers)
        self.app = self.tools.get_mcp_app()
        self.http_app = None
        self.http_server = None
        self.http_thread = None

    async def start_http(self):
        """Start the MCP server in a separate thread"""
        def run_mcp_server():
            try:
                logger.info(f"Starting MCP server on {self.host}:{self.port}")

                # Create server config
                self.http_app = self.app.http_app()
                config = uvicorn.Config(
                    self.http_app,
                    host=self.host,
                    port=self.port,
                    log_level="error"  # Reduce log noise during tests
                )

                # Create server instance
                self.http_server = uvicorn.Server(config)

                # Run server
                self.http_server.run()

            except Exception as e:
                logger.warning(f"MCP server failed to start on {self.host}:{self.port}: {e}")
                # Don't crash the whole server if MCP fails - this is important for tests

        # Run MCP server in separate thread
        self.http_thread = threading.Thread(target=run_mcp_server, daemon=True)
        self.http_thread.start()
        logger.info(f"MCP server thread started for {self.host}:{self.port}")

        # Give MCP server time to start (reduced time for faster tests)
        await asyncio.sleep(0.5)

    def stop_http(self):
        """Stop the MCP server gracefully"""
        if self.http_server:
            try:
                logger.info("Stopping MCP server...")

                # Signal server to shutdown
                self.http_server.should_exit = True

                # Wait for thread to finish with timeout
                if self.http_thread and self.http_thread.is_alive():
                    self.http_thread.join(timeout=5.0)

                    if self.http_thread.is_alive():
                        logger.warning("MCP server thread did not stop gracefully within timeout")
                    else:
                        logger.info("MCP server stopped gracefully")

                # Clean up references
                self.http_server = None
                self.http_thread = None

            except Exception as e:
                logger.warning(f"Error stopping MCP server: {e}")

    def live_mcp_session_ids(self):
        """Sessions of the MCP clients still connected, or None if that cannot be told

        None and the empty set mean different things: None is "no answer
        available" and must not be read as "every client has gone".

        `_server_instances` is private to the MCP SDK's
        StreamableHTTPSessionManager, and fastmcp reaches into it the same way in
        its own shutdown path. A terminated session stays in that dict rather than
        being removed, so `is_terminated` is what separates a client that has gone
        from one that is merely quiet.
        """
        app = self.http_app
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

    async def serve_stdio(self):
        """Run MCP until the client closes stdin; stdout is protocol-only."""
        await self.app.run_async(transport="stdio", show_banner=False)

    async def close(self):
        """Release frontend-owned HTTP resources and file grants."""
        self.stop_http()
        await asyncio.to_thread(self.file_transfers.close)
