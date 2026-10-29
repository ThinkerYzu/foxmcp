"""
Test configuration constants for FoxMCP testing
Ports come from port_coordinator, which assigns a fixed port per server role
"""

import websockets

from port_coordinator import get_port_by_type

# Stands in for a real extension's origin when a test opens the socket itself.
#
# The server accepts only moz-extension:// origins, so a plain
# websockets.connect() is refused with a 403 - correctly, since that is the
# check that keeps web pages out. Tests that impersonate the extension have to
# look like one. The UUID is arbitrary: the server matches the scheme prefix,
# because Firefox assigns a different UUID to every install.
EXTENSION_TEST_ORIGIN = 'moz-extension://f0e1d2c3-b4a5-4968-8778-6a5b4c3d2e1f'

DEFAULT_TEST_CONFIG = {
    'test_timeout': 10.0,    # Default test timeout
    'server_startup_wait': 0.5,  # Time to wait for server startup
}

FIREFOX_TEST_CONFIG = {
    'profile_name': 'foxmcp-test-profile',
    'extension_install_wait': 3.0,  # Time for extension to install and connect
    'firefox_startup_wait': 5.0,    # Time for Firefox to fully start
}

def get_test_ports(suite_name):
    """Get the main websocket and MCP ports; suite_name is accepted but not used"""
    return {
        'websocket': get_port_by_type('websocket'),
        'mcp': get_port_by_type('mcp')
    }

def get_available_port_range(suite_name):
    """Get the websocket port as a single-port range, for callers that still expect a range"""
    # Return the websocket port as a single-port range (for backward compatibility)
    websocket_port = get_port_by_type('websocket')
    return (websocket_port, websocket_port)

# Backward compatibility - kept for existing tests
def get_firefox_test_port():
    """Get the websocket port used by Firefox extension tests"""
    ports = get_test_ports('integration_basic')
    return ports['websocket']

# Legacy TEST_PORTS for backward compatibility
def _get_test_ports_dict():
    """Build the legacy TEST_PORTS dictionary from the assigned ports"""
    return {
        'integration': get_test_ports('integration_basic'),              # Shared by Firefox and WebSocket server tests
        'integration_mcp': get_test_ports('integration_mcp'),            # MCP protocol functionality tests
    }

TEST_PORTS = _get_test_ports_dict()

# Only test clients use this map, to explicitly address their simulated peer.
connected_test_profiles = {}


class TestExtensionConnection:
    """A simulated extension with the real profile handshake and server greeting."""
    __test__ = False

    def __init__(self, uri, profile_id=None, **kwargs):
        import uuid
        from urllib.parse import urlsplit
        self.uri, self.kwargs = uri, kwargs
        self.profile_id = profile_id or str(uuid.uuid4())
        self.port = urlsplit(uri).port
        self.greeting = None

    async def connect(self):
        import asyncio
        import json
        from server.browser_proxy import PROTOCOL_VERSION
        from server.version import VERSION
        self.socket = await websockets.connect(self.uri, additional_headers={
            'Origin': EXTENSION_TEST_ORIGIN}, **self.kwargs)
        self.greeting = await asyncio.wait_for(self.socket.recv(), 5)
        await self.socket.send(json.dumps({'type': 'hello', 'data': {
            'version': VERSION, 'protocol_version': PROTOCOL_VERSION,
            'profile_id': self.profile_id}}))
        ready = json.loads(await asyncio.wait_for(self.socket.recv(), 5))
        assert ready['type'] == 'ready', ready
        connected_test_profiles.setdefault(self.port, set()).add(self.profile_id)
        return self

    def __await__(self):
        return self.connect().__await__()

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *args):
        await self.close()

    def __getattr__(self, name):
        return getattr(self.socket, name)

    async def close(self, *args, **kwargs):
        connected_test_profiles.get(self.port, set()).discard(self.profile_id)
        await self.socket.close(*args, **kwargs)

    async def recv(self):
        if self.greeting is not None:
            greeting, self.greeting = self.greeting, None
            return greeting
        return await self.socket.recv()

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.recv()
        except websockets.ConnectionClosedOK:
            raise StopAsyncIteration


def connect_as_extension(uri, **kwargs):
    """Connect and register a disposable simulated Firefox profile."""
    return TestExtensionConnection(uri, **kwargs)


def profile_connection(server):
    """Explicitly select the sole connection in a single-profile test fixture."""
    from server.browser_profile import BrowserProfile
    if isinstance(server, BrowserProfile):
        return server
    assert len(server.profiles) == 1, 'Test must explicitly choose one Firefox profile'
    return next(iter(server.profiles.values()))
