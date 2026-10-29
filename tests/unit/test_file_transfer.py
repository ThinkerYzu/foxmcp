"""Exercise the actual localhost listener and its one-use file grants."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from urllib.parse import urlsplit

import pytest

import test_imports
from server.file_transfer import FileTransferServer
from server.mcp_tools import FoxMCPTools
from server.server import FoxMCPServer


def download(url, **headers):
    target = urlsplit(url)
    connection = http.client.HTTPConnection(target.hostname, target.port, timeout=5)
    try:
        connection.request("GET", target.path, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


@pytest.fixture
def service():
    result = FileTransferServer()
    yield result
    result.close()


def test_download_preserves_bytes_without_exposing_path(service, tmp_path):
    folder = tmp_path / "private-directory"
    folder.mkdir()
    path = folder / 'résumé "2026".pdf'
    contents = bytes(range(256)) * 8193
    path.write_bytes(contents)
    token, url, metadata = service.grant(str(path))

    assert metadata == {"name": path.name, "type": "application/pdf", "size": len(contents),
                        "lastModified": path.stat().st_mtime_ns // 1_000_000}
    assert path.name not in url and str(tmp_path) not in url
    status, headers, body = download(url)
    assert status == 200
    assert body == contents
    assert headers["Content-Type"] == "application/pdf"
    assert headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in headers
    assert str(tmp_path) not in json.dumps(headers)
    assert download(url)[0] == 404
    service.revoke(token)


@pytest.mark.parametrize("mime, expected", [(None, "application/octet-stream"),
                                            ("IMAGE/PNG", "image/png")])
def test_empty_file_and_mime_override(service, tmp_path, mime, expected):
    path = tmp_path / "file.unknown-foxmcp-extension"
    path.touch()
    _, url, metadata = service.grant(path, mime)
    assert metadata["type"] == expected
    assert download(url)[2] == b""


@pytest.mark.parametrize("headers", [{"Origin": "https://example.org"},
                                      {"Origin": "null"},
                                      {"Host": "example.org"},
                                      {"Sec-Fetch-Dest": "document"}])
def test_browser_page_requests_do_not_consume_grant(service, tmp_path, headers):
    path = tmp_path / "data.txt"
    path.write_bytes(b"private")
    _, url, _ = service.grant(path)
    assert download(url, **headers)[0] == 403
    assert download(url, Origin="moz-extension://test-uuid")[2] == b"private"


def test_expiration_and_revocation_close_descriptors(service, tmp_path):
    path = tmp_path / "data.txt"
    path.write_bytes(b"private")
    service.GRANT_SECONDS = 0
    token, url, _ = service.grant(path)
    handle = service._grants[token].file
    assert download(url)[0] == 404
    assert handle.closed
    service.GRANT_SECONDS = 60
    token, url, _ = service.grant(path)
    handle = service._grants[token].file
    service.revoke(token)
    assert handle.closed
    assert download(url)[0] == 404


def test_rejects_nonregular_files_and_invalid_mime_before_listening(service, tmp_path):
    with pytest.raises(ValueError, match="regular file"):
        service.grant(tmp_path)
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        with pytest.raises(ValueError, match="regular file"):
            service.grant(fifo)
    for mime in ("text/plain\r\nX-Injected: yes", "bogus", "text/☃", ""):
        with pytest.raises(ValueError, match="MIME"):
            service.grant(tmp_path / "missing", mime)
    with pytest.raises(FileNotFoundError):
        service.grant(tmp_path / "missing")
    assert service._http is None


def test_shutdown_releases_listener_and_pending_files(service, tmp_path):
    path = tmp_path / "data.txt"
    path.write_bytes(b"private")
    token, _, _ = service.grant(path)
    handle = service._grants[token].file
    service.close()
    assert handle.closed
    assert not service._thread.is_alive()
    assert service._http.socket.fileno() == -1
    with pytest.raises(RuntimeError, match="closed"):
        service.grant(path)


def test_replacing_path_does_not_change_granted_file(service, tmp_path):
    path = tmp_path / "data.txt"
    path.write_bytes(b"original")
    _, url, _ = service.grant(path)
    path.rename(tmp_path / "old.txt")
    path.write_bytes(b"replacement")
    assert download(url)[2] == b"original"


def test_concurrent_reads_consume_grant_once(service, tmp_path):
    path = tmp_path / "data.txt"
    path.write_bytes(b"private")
    _, url, _ = service.grant(path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(download, [url, url]))
    assert sorted(result[0] for result in results) == [200, 404]


def test_truncation_is_an_incomplete_response(service, tmp_path):
    path = tmp_path / "data.txt"
    path.write_bytes(b"original")
    _, url, _ = service.grant(path)
    path.write_bytes(b"short")
    with pytest.raises(http.client.IncompleteRead):
        download(url)


def test_pending_limit_recovers_after_revocation(service, tmp_path):
    path = tmp_path / "data.txt"
    path.touch()
    service.MAX_PENDING = 1
    token, _, _ = service.grant(path)
    with pytest.raises(ValueError, match="Too many"):
        service.grant(path)
    service.revoke(token)
    _, url, _ = service.grant(path)
    assert download(url)[0] == 200


@pytest.mark.asyncio
async def test_tool_transfers_metadata_and_revokes_url(tmp_path):
    class Bridge:
        file_transfers = FileTransferServer()

        async def send_request_and_wait(self, request, timeout):
            self.request = request
            self.url = request["data"]["url"]
            assert timeout == 120
            assert str(tmp_path) not in json.dumps(request)
            assert (await asyncio.to_thread(download, self.url))[2] == b"hello"
            return {"type": "response", "data": {"fileId": request["data"]["fileId"]}}

    bridge = Bridge()
    path = tmp_path / "hello.txt"
    path.write_bytes(b"hello")
    try:
        tools = FoxMCPTools(bridge)
        tool = await tools.mcp.get_tool("content_load_file")
        result = json.loads(await tool.fn(profile_id="test-profile", tab_id=7, path=str(path), mime_type="text/markdown"))
        assert result["name"] == "hello.txt"
        assert result["type"] == "text/markdown"
        assert result["size"] == 5
        assert result["file_id"] == bridge.request["data"]["fileId"]
        assert str(tmp_path) not in json.dumps(result)
        assert tools.group_by_tool["content_load_file"] == "content"
        assert (await asyncio.to_thread(download, bridge.url))[0] == 404
    finally:
        bridge.file_transfers.close()


@pytest.mark.asyncio
async def test_tool_failure_closes_unclaimed_grant(tmp_path):
    class Bridge:
        file_transfers = FileTransferServer()

        async def send_request_and_wait(self, request, timeout):
            self.url = request["data"]["url"]
            return {"error": "No extension connection available"}

    bridge = Bridge()
    path = tmp_path / "hello.txt"
    path.write_bytes(b"hello")
    try:
        tool = await FoxMCPTools(bridge).mcp.get_tool("content_load_file")
        assert "No extension" in await tool.fn(profile_id="test-profile", tab_id=7, path=str(path))
        assert not bridge.file_transfers._grants
        assert (await asyncio.to_thread(download, bridge.url))[0] == 404
    finally:
        bridge.file_transfers.close()


@pytest.mark.asyncio
async def test_server_shutdown_closes_file_service(tmp_path):
    server = FoxMCPServer(start_mcp=False, use_stdio=True)
    path = tmp_path / "hello.txt"
    path.touch()
    server.file_transfers.grant(path)
    await server._stop()
    assert not server.file_transfers._thread.is_alive()


@pytest.mark.asyncio
async def test_content_group_controls_local_file_tool():
    tools = FoxMCPTools(None, disabled_groups=["content"])
    assert "content_load_file" not in {tool.name for tool in await tools.mcp.list_tools()}
    tools = FoxMCPTools(None, disabled_groups=["content"], enabled_tools=["content_load_file"])
    assert "content_load_file" in {tool.name for tool in await tools.mcp.list_tools()}
