"""Host authorities and Origin policies for the shared browser listener."""

from unittest.mock import Mock

import pytest
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

import test_imports
from server.browser_proxy import BrowserProxyHub


@pytest.fixture
def access():
    hub = BrowserProxyHub(Mock(port=8765))

    def check(path="/discovery", hosts=("localhost:9000",), origins=(),
              peer="127.0.0.1"):
        headers = Headers([("Upgrade", "websocket")])
        for host in hosts:
            headers["Host"] = host
        for origin in origins:
            headers["Origin"] = origin
        connection = Mock(remote_address=(peer, 12345))
        connection.respond.side_effect = lambda status, body: Response(
            status, status.phrase, Headers({"Content-Type": "text/plain"}), body.encode()
        )
        return hub.process_request(connection, Request(path, headers))

    return check


@pytest.mark.parametrize("host", [
    "localhost", "LOCALHOST:9000", "localhost:1", "localhost:65535",
    "127.0.0.1", "127.0.0.1:9000", "[::1]", "[::1]:9000",
])
def test_local_authorities_accept_independent_ports(access, host):
    assert access(hosts=(host,)).status_code == 200


@pytest.mark.parametrize("host", [
    "", "example.org:9000", "localhost.example.org", "localhost.",
    "127.0.0.2", "127.1", "::1", "[::2]", "[::1", "::1]",
    "localhost:", "localhost:0", "localhost:65536", "localhost:999999",
    "localhost:-1", "localhost:+80", "localhost:abc", "localhost:\xb2",
    "http://localhost:80", "user@localhost", "localhost@127.0.0.1",
    "localhost/path", "localhost?query", "localhost#fragment",
    " localhost", "localhost ", "localhost:80:90",
])
@pytest.mark.parametrize("path", ["/", "/discovery", "/proxy"])
def test_invalid_host_authorities_are_rejected(access, host, path):
    origins = ("moz-extension://test-uuid",) if path == "/" else ()
    assert access(path, hosts=(host,), origins=origins).status_code == 403


@pytest.mark.parametrize("hosts", [(), ("localhost", "localhost")])
def test_exactly_one_host_is_required(access, hosts):
    assert access(hosts=hosts).status_code == 403


@pytest.mark.parametrize("peer", ["192.0.2.1", "2001:db8::1"])
def test_non_loopback_peers_are_rejected(access, peer):
    assert access(peer=peer).status_code == 403


@pytest.mark.parametrize("origins", [
    (), ("https://example.org",), ("null",), ("",), ("moz-extension://",),
    ("moz-extension://one", "moz-extension://two"),
])
def test_extension_requires_one_extension_origin(access, origins):
    assert access("/", origins=origins).status_code == 403


def test_extension_origin_is_accepted_through_a_forwarded_port(access):
    assert access("/", origins=("moz-extension://test-uuid",)) is None


@pytest.mark.parametrize("path", ["/discovery", "/proxy"])
@pytest.mark.parametrize("origin", ["", "null", "https://example.org",
                                    "moz-extension://test-uuid"])
def test_discovery_and_proxy_reject_every_origin(access, path, origin):
    assert access(path, origins=(origin,)).status_code == 403


def test_proxy_accepts_local_client_without_origin(access):
    assert access("/proxy") is None
