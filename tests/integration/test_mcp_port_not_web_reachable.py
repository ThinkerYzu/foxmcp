"""
Tests that a web page cannot reach the MCP port

The MCP port has no authentication: anything able to send it a request can call
every tool, including content_execute_predefined. That is accepted for local
processes, which already hold the browser profile and the script directory. It
is not acceptable for a web page, which reaches localhost from inside the
user's own browser.

Three things currently keep pages out, and FoxMCP wrote none of them - they are
behavior of fastmcp, the MCP SDK and uvicorn:

1. No CORS headers, so the browser blocks any preflighted request
2. Content-Type enforcement, which closes the simple-request bypass that would
   otherwise skip the preflight entirely
3. A session id the browser cannot read cross-origin

Relying on a dependency for a security property is only safe if the property is
checked. These tests are that check. The `fastmcp` floor in requirements.txt
has already drifted several major versions once without anyone noticing, so a
future upgrade quietly re-opening this is a real path, not a hypothetical.

If one of these fails after a dependency bump, the port has become reachable
from any page the user visits, and the fix is a deliberate CORS policy - not a
loosened assertion.
"""

import asyncio

import httpx
import pytest
import pytest_asyncio

import test_imports  # Automatic path setup
from server.server import FoxMCPServer
from port_coordinator import get_port_by_type

# Stands in for any site the user might have open in another tab.
PAGE_ORIGIN = 'https://evil.example.com'


@pytest_asyncio.fixture
async def mcp_url():
    """Run a server with MCP enabled and yield its endpoint URL

    No Firefox and no extension: these tests only exercise the HTTP surface,
    which answers regardless of whether a browser is connected.
    """
    server = FoxMCPServer(
        host="localhost",
        port=get_port_by_type('test_individual'),
        mcp_port=get_port_by_type('test_mcp_individual'),
        start_mcp=True
    )
    server_task = asyncio.create_task(server.start_server())

    # Poll rather than sleep a fixed interval; uvicorn starts on its own thread.
    url = f"http://localhost:{server.mcp_port}/mcp"
    async with httpx.AsyncClient() as probe:
        for _ in range(50):
            try:
                await probe.get(url, timeout=1.0)
                break
            except httpx.HTTPError:
                await asyncio.sleep(0.2)
        else:
            pytest.fail(f"MCP server never came up on {url}")

    yield url

    await server.shutdown(server_task)


def assert_no_cors_headers(response):
    """Fail if the response would let a cross-origin page read it

    access-control-allow-origin is the single header that matters: without it
    the browser discards the response and blocks preflighted requests outright,
    whatever the status code says.
    """
    header_names = {name.lower() for name in response.headers}
    assert 'access-control-allow-origin' not in header_names, (
        f"MCP endpoint sent access-control-allow-origin: "
        f"{response.headers.get('access-control-allow-origin')!r} - a web page can now reach it"
    )


class TestMCPPortRejectsWebPages:

    @pytest.mark.asyncio
    async def test_preflight_gets_no_cors_headers(self, mcp_url):
        """The preflight a browser sends first must not be answered permissively"""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                'OPTIONS',
                mcp_url,
                headers={
                    'Origin': PAGE_ORIGIN,
                    'Access-Control-Request-Method': 'POST',
                    'Access-Control-Request-Headers': 'content-type',
                }
            )

        assert_no_cors_headers(response)

    @pytest.mark.asyncio
    async def test_json_post_gets_no_cors_headers(self, mcp_url):
        """A normal MCP call carrying a page Origin must not be readable by it"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                mcp_url,
                headers={
                    'Origin': PAGE_ORIGIN,
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, text/event-stream',
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            )

        assert_no_cors_headers(response)

    @pytest.mark.asyncio
    async def test_simple_request_bypass_is_rejected(self, mcp_url):
        """text/plain skips the preflight entirely, so the server must refuse it

        This is the assertion that matters most. CORS only stops a page from
        *reading* the response, and calling content_execute_predefined is
        already the whole attack - the caller never needs to see the reply. A
        text/plain body is a CORS "simple request": no preflight, the browser
        just sends it. Content-Type enforcement is what closes that path.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                mcp_url,
                headers={
                    'Origin': PAGE_ORIGIN,
                    'Content-Type': 'text/plain',
                    'Accept': 'application/json, text/event-stream',
                },
                content='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
            )

        assert response.status_code == 400
        assert 'content-type' in response.text.lower()
        assert_no_cors_headers(response)

    @pytest.mark.asyncio
    async def test_tool_call_needs_a_session_the_browser_cannot_read(self, mcp_url):
        """Without a session id, tool calls are refused

        The id is handed out in a response header, which cross-origin
        JavaScript cannot read - so even a page that got a request through
        could not carry on a conversation.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                mcp_url,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, text/event-stream',
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            )

        assert response.status_code == 400
        assert 'session' in response.text.lower()

    @pytest.mark.asyncio
    async def test_no_tool_names_leak_to_an_unauthenticated_caller(self, mcp_url):
        """A refused call must not enumerate the tool surface on its way out"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                mcp_url,
                headers={
                    'Origin': PAGE_ORIGIN,
                    'Content-Type': 'application/json',
                    'Accept': 'application/json, text/event-stream',
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            )

        assert 'content_execute_predefined' not in response.text
        assert 'tabs_list' not in response.text
