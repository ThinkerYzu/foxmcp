"""
Tests for --stdio, the transport an MCP client can launch itself

These drive the real `server/server.py` as a subprocess and speak JSON-RPC on its
stdin and stdout, because that is the whole point of the mode: nothing here can be
checked by calling into the server in-process. The two things that break stdio
servers in practice are output on stdout that is not JSON-RPC, and a process that
does not exit when its client hangs up, so both have tests of their own.

The extension side is unchanged in stdio mode - the WebSocket server still listens
on its port - and test_a_tool_call_reaches_the_extension is what proves the two
halves are still connected when the MCP half is a pipe rather than a socket.
"""

import asyncio
import json
import os
import socket
import sys

import pytest
import pytest_asyncio

import test_imports  # Automatic path setup
from port_coordinator import get_port_by_type
from test_config import connect_as_extension


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER_SCRIPT = os.path.join(REPO_ROOT, 'server', 'server.py')

# Long enough for a Python interpreter to start and import fastmcp on a loaded CI
# runner, short enough that a hung server fails the test rather than the job.
REPLY_TIMEOUT = 30.0


class StdioClient:
    """The server as an MCP client meets it: a process speaking JSON-RPC over pipes

    Collects stderr separately so that a test can assert where the logging went;
    it is drained only at close(), which is safe because the server logs a few
    lines, not a stream.
    """

    def __init__(self, websocket_port, extra_args=()):
        self.websocket_port = websocket_port
        self.extra_args = list(extra_args)
        self.process = None
        self.stdout_lines = []
        self.stderr_text = ''
        self._next_id = 0

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, SERVER_SCRIPT, '--stdio', '--port', str(self.websocket_port),
            *self.extra_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=REPO_ROOT,
        )
        return self

    async def initialize(self):
        """Perform the handshake every MCP client performs before anything else"""
        result = await self.request('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'foxmcp-tests', 'version': '0'},
        })
        await self.notify('notifications/initialized')
        return result

    async def request(self, method, params=None):
        self._next_id += 1
        request_id = self._next_id
        await self._send({'jsonrpc': '2.0', 'id': request_id,
                          'method': method, 'params': params or {}})

        message = await self._receive()
        assert message.get('id') == request_id, \
            f"Reply is for a different request: {message}"
        assert 'error' not in message, f"{method} returned an error: {message['error']}"
        return message['result']

    async def notify(self, method, params=None):
        await self._send({'jsonrpc': '2.0', 'method': method, 'params': params or {}})

    async def list_tool_names(self):
        return {tool['name'] for tool in (await self.request('tools/list'))['tools']}

    async def call_tool(self, name, arguments=None):
        """Call one tool and return the text of its result"""
        result = await self.request('tools/call',
                                    {'name': name, 'arguments': arguments or {}})
        return '\n'.join(block['text'] for block in result['content']
                         if block['type'] == 'text')

    async def _send(self, message):
        self.process.stdin.write((json.dumps(message) + '\n').encode())
        await self.process.stdin.drain()

    async def _receive(self):
        line = await asyncio.wait_for(self.process.stdout.readline(), REPLY_TIMEOUT)
        assert line, f"Server closed stdout without replying. stderr:\n{await self._read_stderr()}"
        self.stdout_lines.append(line.decode())
        return json.loads(line)

    async def _read_stderr(self):
        if not self.stderr_text:
            self.stderr_text = (await self.process.stderr.read()).decode()
        return self.stderr_text

    async def close(self, timeout=15.0):
        """Close stdin the way a departing client does, and return the exit code"""
        if self.process.returncode is None:
            self.process.stdin.close()
        try:
            await asyncio.wait_for(self.process.wait(), timeout)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()
            pytest.fail(f"Server did not exit when its client closed stdin. "
                        f"stderr:\n{await self._read_stderr()}")
        finally:
            await self._read_stderr()
        return self.process.returncode


@pytest.fixture
def websocket_port():
    return get_port_by_type('test_individual')


@pytest_asyncio.fixture
async def stdio_client(websocket_port):
    """A started, initialized server; closed at the end of the test"""
    client = await StdioClient(websocket_port).start()
    await client.initialize()
    yield client
    await client.close()


class TestServingOverStdio:
    """What a client that launched the server can do with it"""

    @pytest.mark.asyncio
    async def test_the_tools_are_offered(self, stdio_client):
        """tools/list over stdio offers the same surface HTTP mode does"""
        names = await stdio_client.list_tool_names()

        assert 'tabs_list' in names
        assert len(names) > 30, f"Only {len(names)} tools offered: {sorted(names)}"

    @pytest.mark.asyncio
    async def test_a_tool_call_reaches_the_extension(self, stdio_client, websocket_port):
        """The bridge still works when the MCP half is a pipe

        A fake extension answers tabs.list on the WebSocket the server is still
        listening on, and the tab it reports has to come back through stdout. This
        is the test that would fail if stdio mode served MCP without the WebSocket
        server behind it.
        """
        async with connect_as_extension(f"ws://localhost:{websocket_port}") as extension:
            await asyncio.sleep(0.2)

            call = asyncio.create_task(stdio_client.call_tool('tabs_list'))

            greeting = json.loads(await asyncio.wait_for(extension.recv(), REPLY_TIMEOUT))
            assert greeting['type'] == 'hello'
            request = json.loads(await asyncio.wait_for(extension.recv(), REPLY_TIMEOUT))
            assert request['action'] == 'tabs.list'

            await extension.send(json.dumps({
                'id': request['id'],
                'type': 'response',
                'action': 'tabs.list',
                'data': {'tabs': [{'id': 7, 'url': 'https://example.org/',
                                   'title': 'Example', 'active': True,
                                   'windowId': 1, 'index': 0}]},
            }))

            listing = await asyncio.wait_for(call, REPLY_TIMEOUT)

        assert 'ID 7' in listing and 'https://example.org/' in listing, \
            f"The extension's tab should have reached the client: {listing}"

    @pytest.mark.asyncio
    async def test_disabling_tool_groups_still_applies(self, websocket_port):
        """--stdio composes with the options that shape the tool surface"""
        client = await StdioClient(websocket_port,
                                   ['--disable-tools', 'bookmarks,history']).start()
        try:
            await client.initialize()
            names = await client.list_tool_names()
        finally:
            await client.close()

        assert 'tabs_list' in names
        assert not [name for name in names
                    if name.startswith(('bookmarks_', 'history_'))], sorted(names)



class TestBeforeTheExtensionConnects:
    """The window stdio mode opens, and that the server comes out of it

    The extension dials the server, not the other way round, and it retries on a
    timer. Under --stdio the server is started by the MCP client, so a client that
    launches one and calls a tool straight away can arrive before the extension
    has reconnected. Both tests run with no extension attached at all, which is
    that window held open.
    """

    # The tool path answers from state rather than waiting on the extension, so
    # this is loose enough for a loaded runner and still far below the 30s a
    # request that actually waited for a reply would take.
    FAIL_FAST_SECONDS = 10.0

    @pytest.mark.asyncio
    async def test_a_tool_call_with_no_extension_fails_instead_of_waiting(self, stdio_client):
        """The client gets an answer in the gap, not a stall

        docs/configuration.md tells users the call "returns No extension connection
        available immediately rather than waiting for the browser", and to run it
        again. Waiting instead would strand the client for the request timeout with
        nothing to show, which is the failure this asserts against.
        """
        started = asyncio.get_event_loop().time()
        answer = await stdio_client.call_tool('tabs_list')
        elapsed = asyncio.get_event_loop().time() - started

        assert 'No extension connection' in answer, \
            f"Expected the missing-extension error, got: {answer}"
        assert elapsed < self.FAIL_FAST_SECONDS, \
            f"Took {elapsed:.1f}s to say the extension is not connected"

    @pytest.mark.asyncio
    async def test_the_extension_is_served_once_it_arrives(self, stdio_client, websocket_port):
        """A call that failed early must not spoil the ones after it

        This is the sequence a user actually hits: the client starts the server,
        asks for something before Firefox has reconnected, and asks again a moment
        later. The second call has to reach the browser, so nothing about the first
        may leave the bridge unusable - a pending request never cleaned up, or a
        connection slot marked taken.
        """
        assert 'No extension connection' in await stdio_client.call_tool('tabs_list')

        async with connect_as_extension(f"ws://localhost:{websocket_port}") as extension:
            await asyncio.sleep(0.2)

            call = asyncio.create_task(stdio_client.call_tool('tabs_list'))

            greeting = json.loads(await asyncio.wait_for(extension.recv(), REPLY_TIMEOUT))
            assert greeting['type'] == 'hello'
            request = json.loads(await asyncio.wait_for(extension.recv(), REPLY_TIMEOUT))
            assert request['action'] == 'tabs.list'

            await extension.send(json.dumps({
                'id': request['id'],
                'type': 'response',
                'action': 'tabs.list',
                'data': {'tabs': [{'id': 3, 'url': 'https://example.net/',
                                   'title': 'Late arrival', 'active': True,
                                   'windowId': 1, 'index': 0}]},
            }))

            listing = await asyncio.wait_for(call, REPLY_TIMEOUT)

        assert 'ID 3' in listing and 'https://example.net/' in listing, \
            f"The extension that connected late should still be served: {listing}"


class TestStdoutCarriesOnlyTheProtocol:
    """One stray line on stdout ends the session, so this is the mode's one rule"""

    @pytest.mark.asyncio
    async def test_every_line_of_stdout_is_json_rpc(self, stdio_client):
        """Nothing else may be written there - not a banner, not a log line"""
        await stdio_client.list_tool_names()
        await stdio_client.call_tool('tabs_list')  # Fails; the reply is still JSON-RPC

        for line in stdio_client.stdout_lines:
            message = json.loads(line)
            assert message.get('jsonrpc') == '2.0', f"Not a JSON-RPC message: {line}"

    @pytest.mark.asyncio
    async def test_the_logging_went_to_stderr(self, stdio_client):
        """The server is not silent - it says the same things, on the other stream"""
        await stdio_client.close()

        assert 'FoxMCP WebSocket server is running' in stdio_client.stderr_text, \
            f"stderr should carry the startup log:\n{stdio_client.stderr_text}"

    @pytest.mark.asyncio
    async def test_the_history_tool_writes_nothing_to_stdout(self, stdio_client,
                                                             websocket_port):
        """history_get_recent used to print its whole response to stdout

        It was debug output that predates stdio mode, and under stdio it would have
        broken the connection on the first call. The tool is exercised with a real
        reply, which is what that print() was in the path of.
        """
        async with connect_as_extension(f"ws://localhost:{websocket_port}") as extension:
            await asyncio.sleep(0.2)

            call = asyncio.create_task(stdio_client.call_tool('history_get_recent',
                                                              {'count': 1}))
            greeting = json.loads(await asyncio.wait_for(extension.recv(), REPLY_TIMEOUT))
            assert greeting['type'] == 'hello'
            request = json.loads(await asyncio.wait_for(extension.recv(), REPLY_TIMEOUT))
            await extension.send(json.dumps({
                'id': request['id'],
                'type': 'response',
                'action': request['action'],
                'data': {'items': [{'url': 'https://example.org/',
                                    'title': 'Example',
                                    'lastVisitTime': 1700000000000,
                                    'visitCount': 1}]},
            }))
            await asyncio.wait_for(call, REPLY_TIMEOUT)

        for line in stdio_client.stdout_lines:
            assert json.loads(line).get('jsonrpc') == '2.0', f"Not JSON-RPC: {line}"


class TestLifetime:
    """A launched server lives and dies with the client that launched it"""

    @pytest.mark.asyncio
    async def test_closing_stdin_stops_the_server_and_frees_the_port(self, websocket_port):
        """The client hanging up has to release the extension port, not just exit

        A server that exits while its listening socket is still held would stop the
        next client the user's MCP config launches, which in stdio mode is every
        restart of their editor.
        """
        client = await StdioClient(websocket_port).start()
        await client.initialize()

        assert await client.close() == 0

        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('localhost', websocket_port))

    @pytest.mark.asyncio
    async def test_a_taken_websocket_port_fails_loudly(self, websocket_port):
        """Only one server can serve the extension, and the second must say so

        Easy to hit in stdio mode, where every MCP client launches a server of its
        own. The exit code is what the client reports; the message is for the log
        the user goes looking at afterwards.
        """
        with socket.socket() as holder:
            holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            holder.bind(('localhost', websocket_port))
            holder.listen(1)

            client = await StdioClient(websocket_port).start()
            client.process.stdin.close()
            await asyncio.wait_for(client.process.wait(), 30.0)
            stderr = (await client.process.stderr.read()).decode()
            stdout = await client.process.stdout.read()

        assert client.process.returncode != 0, "A server that cannot listen has failed"
        assert stdout == b'', f"Nothing may be written to stdout: {stdout!r}"
        assert 'Another FoxMCP server is most likely already running' in stderr, stderr


class TestOptionsThatCannotBeCombined:
    """Options that would silently do nothing are refused instead"""

    async def run_with(self, *args):
        process = await asyncio.create_subprocess_exec(
            sys.executable, SERVER_SCRIPT, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=REPO_ROOT,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), 30.0)
        return process.returncode, stdout.decode(), stderr.decode()

    @pytest.mark.asyncio
    async def test_stdio_with_no_mcp_is_refused(self):
        """--no-mcp would leave stdio mode with nothing to serve"""
        returncode, _, stderr = await self.run_with('--stdio', '--no-mcp')

        assert returncode != 0
        assert '--stdio and --no-mcp cannot be combined' in stderr

    @pytest.mark.asyncio
    async def test_stdio_with_an_mcp_port_is_refused(self):
        """--mcp-port names a listener stdio mode never opens"""
        returncode, _, stderr = await self.run_with('--stdio', '--mcp-port', '4000')

        assert returncode != 0
        assert '--mcp-port has no meaning with --stdio' in stderr
