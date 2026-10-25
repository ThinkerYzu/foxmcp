"""
Tests for what stdio mode changes inside the server, short of running it

The transport itself is covered by tests/integration/test_stdio_transport.py,
which drives a real process. What is left here is the part that has no output to
observe: the MCP port that stdio mode must not go looking for, and the rule that
nothing in server/ may write to stdout, which is easy to break by accident a year
from now and impossible to see in a test that does not use stdio.
"""

import ast
import os

import pytest

import test_imports  # Automatic path setup
from server.server import FoxMCPServer


SERVER_PACKAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'server'
)


class TestNoMcpPortInStdioMode:
    """stdio mode opens no HTTP listener, so it must not claim a port either"""

    def test_stdio_leaves_the_mcp_port_unset(self):
        """None rather than 3000: there is no listener for a port to describe"""
        server = FoxMCPServer(port=8765, use_stdio=True)

        assert server.mcp_port is None
        assert server.use_stdio is True

    def test_stdio_does_not_take_the_port_an_http_server_is_using(self):
        """A running HTTP-mode server is not a conflict for a stdio one

        The port selection bind-tests its candidate and walks past anything in
        use. Doing that in stdio mode would report the user's own other server as
        an obstacle to a listener that is never opened.
        """
        http_server = FoxMCPServer(port=8765, mcp_port=None)
        stdio_server = FoxMCPServer(port=8765, use_stdio=True)

        assert http_server.mcp_port is not None
        assert stdio_server.mcp_port is None

    def test_http_mode_is_unchanged(self):
        """The default is still a port, and stdio is off unless asked for"""
        server = FoxMCPServer(port=8765)

        assert isinstance(server.mcp_port, int)
        assert server.use_stdio is False


class TestNothingWritesToStdout:
    """stdout carries the JSON-RPC framing in stdio mode, and nothing else

    A print() anywhere the server can reach breaks the client's connection at the
    moment that line runs - which for a debug print in one tool means one tool
    call, on one user's machine, with no error that names the cause. Checking the
    source is the only way to catch it before that.
    """

    def print_calls_in(self, path):
        """Line numbers of the print() calls in one file, docstrings excluded

        Parsing rather than grepping is what excludes the two print() calls in
        server.py's docstrings, which are example code for a caller and never run.
        """
        with open(path, encoding='utf-8') as source:
            tree = ast.parse(source.read(), filename=path)

        return [node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 'print']

    @pytest.mark.parametrize('filename', sorted(
        name for name in os.listdir(SERVER_PACKAGE) if name.endswith('.py')
    ))
    def test_no_module_in_the_server_package_prints(self, filename):
        path = os.path.join(SERVER_PACKAGE, filename)
        lines = self.print_calls_in(path)

        assert not lines, (
            f"server/{filename} calls print() at line(s) {lines}. Under --stdio "
            f"stdout carries the MCP protocol; use logger instead."
        )
