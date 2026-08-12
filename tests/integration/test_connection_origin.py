"""
Tests for the origin check on the extension WebSocket

The server accepts only moz-extension:// origins. WebSocket handshakes are
exempt from the same-origin policy and are never preflighted, so without this
check any web page the user visits could connect to the localhost port and be
accepted as the extension - then disconnect the real one, since an arriving
connection displaces the existing one, and answer requests on its behalf.
"""

import asyncio

import pytest
import pytest_asyncio
import websockets

import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from port_coordinator import get_port_by_type
from test_config import EXTENSION_TEST_ORIGIN, connect_as_extension


class TestConnectionOrigin:
    """Only browser extensions may connect as the extension"""

    @pytest_asyncio.fixture
    async def server(self):
        """Run a server with MCP disabled; these tests only exercise the socket"""
        server = FoxMCPServer(
            host="localhost",
            port=get_port_by_type('test_individual'),
            mcp_port=get_port_by_type('test_mcp_individual'),
            start_mcp=False
        )
        server_task = asyncio.create_task(server.start_server())
        await asyncio.sleep(0.5)

        yield server

        await server.shutdown(server_task)

    def uri(self, server):
        return f"ws://localhost:{server.port}"

    @pytest.mark.asyncio
    async def test_extension_origin_is_accepted(self, server):
        """A moz-extension:// origin connects and becomes the extension connection"""
        async with connect_as_extension(self.uri(server)):
            await asyncio.sleep(0.2)
            assert server.extension_connection is not None

    @pytest.mark.asyncio
    async def test_web_page_origin_is_rejected(self, server):
        """A page origin is refused with 403, and never becomes the extension"""
        with pytest.raises(websockets.exceptions.InvalidStatus) as rejection:
            await websockets.connect(
                self.uri(server),
                additional_headers={'Origin': 'https://evil.example.com'}
            )

        assert rejection.value.response.status_code == 403
        assert server.extension_connection is None

    @pytest.mark.asyncio
    async def test_missing_origin_is_rejected(self, server):
        """A client that sends no Origin at all is refused too

        Deliberate: allowing a missing origin would readmit every non-browser
        local client, and the rule is only worth having if it is the tight one.
        This is why tests use connect_as_extension() rather than calling
        websockets.connect() directly.
        """
        with pytest.raises(websockets.exceptions.InvalidStatus) as rejection:
            await websockets.connect(self.uri(server))

        assert rejection.value.response.status_code == 403
        assert server.extension_connection is None

    @pytest.mark.asyncio
    async def test_rejected_page_cannot_displace_the_extension(self, server):
        """The real extension survives a rejected connection attempt

        The single-connection policy closes the existing socket to admit a new
        one, so a rejection that reached handle_extension_connection would be a
        denial of service on its own. The library rejects during the handshake,
        before that code runs.
        """
        async with connect_as_extension(self.uri(server)) as extension:
            await asyncio.sleep(0.2)
            assert server.extension_connection is not None

            with pytest.raises(websockets.exceptions.InvalidStatus):
                await websockets.connect(
                    self.uri(server),
                    additional_headers={'Origin': 'https://evil.example.com'}
                )

            await asyncio.sleep(0.2)
            assert server.extension_connection is not None
            assert extension.close_code is None

    @pytest.mark.asyncio
    async def test_origin_uuid_is_not_pinned(self, server):
        """Any UUID works - Firefox assigns a different one to every install"""
        other_install = 'moz-extension://00000000-1111-2222-3333-444444444444'
        assert other_install != EXTENSION_TEST_ORIGIN

        async with websockets.connect(
            self.uri(server),
            additional_headers={'Origin': other_install}
        ):
            await asyncio.sleep(0.2)
            assert server.extension_connection is not None
