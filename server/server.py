#!/usr/bin/env python3
"""Compose browser ownership and MCP frontends for the selected startup mode."""

import argparse
import asyncio
import logging
import os
import sys

try:
    from .browser_server import BrowserServer, EXTENSION_ORIGIN_PATTERN
    from .mcp_frontend import MCPFrontend, HAS_PORT_COORDINATOR
    from .mcp_tools import FoxMCPTools
except ImportError:
    from browser_server import BrowserServer, EXTENSION_ORIGIN_PATTERN
    from mcp_frontend import MCPFrontend, HAS_PORT_COORDINATOR
    from mcp_tools import FoxMCPTools

# stdout belongs exclusively to the MCP stdio transport.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

# Preserve existing import entry points while exposing the explicit components.
__all__ = ["BrowserServer", "MCPFrontend", "FoxMCPServer", "serve", "main", "run",
           "EXTENSION_ORIGIN_PATTERN", "HAS_PORT_COORDINATOR"]


async def serve(browser_server, frontend=None, *, use_stdio=False):
    """Compose a browser owner with an optional direct MCP frontend."""
    tasks = []
    done = set()
    try:
        # Bind before serving MCP so a losing owner cannot leave a listener alive.
        await browser_server.start_browser_listener()
        if frontend is not None and not use_stdio:
            browser_server.live_mcp_session_ids = frontend.live_mcp_session_ids
            await frontend.start_http()
            browser_server.monitor_reaper_task = asyncio.create_task(
                browser_server._reap_monitors())
        if frontend is not None and use_stdio:
            tasks = [asyncio.create_task(frontend.serve_stdio(), name="foxmcp-stdio"),
                     asyncio.create_task(browser_server.websocket_server.wait_closed(),
                                         name="foxmcp-websocket")]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        else:
            await browser_server.websocket_server.wait_closed()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Preserve shutdown order: reaper, MCP transport, browser sockets, files.
        await browser_server.stop_monitor_reaper()
        if frontend is not None:
            frontend.stop_http()
        await browser_server._stop()
        if frontend is not None:
            await frontend.close()
    for task in done:
        if not task.cancelled() and task.exception() is not None:
            raise task.exception()


class FoxMCPServer(BrowserServer):
    """Compatibility entry point for existing in-process callers and tests.

    New startup code composes BrowserServer and MCPFrontend explicitly. This
    facade retains the old constructor and MCP attributes without duplicating
    the browser registry or frontend resources.
    """

    def __init__(self, host="localhost", port=8765, mcp_port=None, start_mcp=True,
                 disabled_tool_groups=None, enabled_tools=None, use_stdio=False):
        super().__init__(host, port)
        self.start_mcp = start_mcp
        self.use_stdio = use_stdio
        # Existing callers also use the tool definitions with start_mcp=False.
        self.frontend = MCPFrontend(
            self, host=host, port=mcp_port, use_stdio=use_stdio,
            disabled_tool_groups=disabled_tool_groups, enabled_tools=enabled_tools)
        self.live_mcp_session_ids = self.frontend.live_mcp_session_ids

    @property
    def mcp_tools(self):
        return self.frontend.tools

    @property
    def mcp_app(self):
        return self.frontend.app

    @property
    def mcp_port(self):
        return self.frontend.port

    @property
    def mcp_http_app(self):
        return self.frontend.http_app

    @property
    def mcp_server_instance(self):
        return self.frontend.http_server

    @property
    def file_transfers(self):
        return self.frontend.file_transfers

    async def start_mcp_server(self):
        await self.frontend.start_http()

    async def start_server(self):
        await serve(self, self.frontend if self.start_mcp else None,
                    use_stdio=self.use_stdio)

    async def _stop(self):
        await self.stop_monitor_reaper()
        self.frontend.stop_http()
        await super()._stop()
        await self.frontend.close()


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

    # Validate tool names before discovery or worker startup, as in direct mode.
    try:
        FoxMCPTools.validate_selection(disabled_tool_groups, enabled_tools)
    except ValueError as e:
        parser.error(str(e))

    if args.single_instance:
        try:
            from .single_instance import run_proxy, run_worker
        except ImportError:
            from single_instance import run_proxy, run_worker
        if args.single_instance_worker:
            browser_server = BrowserServer(args.host, args.port)
            await run_worker(browser_server, args.single_instance_idle_timeout)
        else:
            await run_proxy(args.host, args.port, args.single_instance_idle_timeout,
                            disabled_tool_groups=disabled_tool_groups,
                            enabled_tools=enabled_tools)
        return

    browser_server = BrowserServer(args.host, args.port)
    frontend = None if args.no_mcp else MCPFrontend(
        browser_server, host=args.host, port=args.mcp_port, use_stdio=args.stdio,
        disabled_tool_groups=disabled_tool_groups, enabled_tools=enabled_tools)
    await serve(browser_server, frontend, use_stdio=args.stdio)


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
