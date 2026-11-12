"""Exercise disk-backed upload grants through actual HTTP and screenshot tools."""

import asyncio
import base64
import hashlib
import http.client
from pathlib import Path
import socket
import time
import tracemalloc
from urllib.parse import urlsplit

import pytest

import test_imports  # noqa: F401
from server.file_transfer import FileTransferServer
from server.mcp_tools import FoxMCPTools


@pytest.fixture
def service():
    owner = FileTransferServer()
    yield owner
    owner.close()


def put(url, body=b"image bytes", request_id="capture", **headers):
    address = urlsplit(url)
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=5)
    try:
        connection.request("PUT", address.path, body, headers={
            "Content-Type": "image/png", "X-FoxMCP-Request-Id": request_id, **headers})
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def reserve(service, tmp_path, request_id="capture", profile=1, **kwargs):
    return service.reserve_upload(request_id, profile, "screenshot", "image/png",
                                  directory=tmp_path, **kwargs)


def test_upload_exact_bytes_one_use_and_cleanup(service, tmp_path):
    token, url, grant = reserve(service, tmp_path)
    contents = bytes(range(256)) * 10000
    assert put(url, contents) == 204
    result = grant.completion.result(1)
    assert result == {"path": grant.path, "size": len(contents), "type": "image/png"}
    assert Path(grant.path).read_bytes() == contents
    assert grant.file.closed
    assert put(url) == 404
    service.revoke(token)
    assert not Path(grant.path).exists()
    assert not service._uploads


@pytest.mark.parametrize("headers", [
    {"Origin": "https://example.org"}, {"Origin": "null"},
    {"Host": "example.org"}, {"Sec-Fetch-Dest": "document"},
    {"Content-Type": "image/jpeg"}, {"X-FoxMCP-Request-Id": "other-request"},
])
def test_upload_rejects_wrong_source_and_correlation_without_consuming(service, tmp_path, headers):
    _, url, grant = reserve(service, tmp_path)
    assert put(url, **headers) == 403
    assert not grant.completion.done()
    assert put(url, Origin="moz-extension://test-uuid") == 204


@pytest.mark.parametrize("headers", [
    {"Content-Length": "bad"}, {"Transfer-Encoding": "chunked"},
])
def test_upload_requires_unambiguous_length(service, tmp_path, headers):
    _, url, _ = reserve(service, tmp_path)
    assert put(url, **headers) == 411
    assert put(url) == 204


def test_upload_concurrent_requests_and_profiles_are_independent(service, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    grants = [reserve(service, tmp_path, f"request-{i}", profile=i + 1) for i in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(put, url, bytes([i]) * 100000, f"request-{i}")
                   for i, (_, url, _) in enumerate(grants)]
        assert [future.result() for future in futures] == [204] * 4
    for i, (_, _, grant) in enumerate(grants):
        assert grant.profile_id == i + 1
        assert Path(grant.completion.result()["path"]).read_bytes() == bytes([i]) * 100000


def test_upload_limit_shared_with_downloads_and_recovered(service, tmp_path):
    service.MAX_PENDING = 1
    token, url, grant = reserve(service, tmp_path)
    with pytest.raises(ValueError, match="Too many"):
        reserve(service, tmp_path)
    path = tmp_path / "download"
    path.write_bytes(b"file")
    with pytest.raises(ValueError, match="Too many"):
        service.grant(path)
    assert put(url) == 204
    with pytest.raises(ValueError, match="Too many"):
        reserve(service, tmp_path)
    service.revoke(token)
    assert not Path(grant.path).exists()
    service.grant(path)


def test_upload_expiry_deletes_staging_and_refuses_late_sender(service, tmp_path):
    _, url, grant = reserve(service, tmp_path, timeout=.01)
    time.sleep(.02)
    assert put(url) == 404
    with pytest.raises(TimeoutError):
        grant.completion.result()
    assert not Path(grant.path).exists()


def partial_upload(url, request_id="capture"):
    address = urlsplit(url)
    peer = socket.create_connection((address.hostname, address.port), timeout=5)
    peer.sendall((f"PUT {address.path} HTTP/1.1\r\nHost: {address.netloc}\r\n"
                  f"Content-Type: image/png\r\nX-FoxMCP-Request-Id: {request_id}\r\n"
                  "Content-Length: 1000000\r\n\r\nshort").encode())
    return peer


def wait_claimed(grant):
    deadline = time.monotonic() + 3
    while not grant.claimed:
        assert time.monotonic() < deadline
        time.sleep(.01)


def test_interrupted_upload_never_completes_and_removes_file(service, tmp_path):
    _, url, grant = reserve(service, tmp_path)
    peer = partial_upload(url)
    wait_claimed(grant)
    peer.shutdown(socket.SHUT_WR)
    with pytest.raises(OSError, match="interrupted"):
        grant.completion.result(3)
    peer.close()
    # Completion failure and cleanup happen under the same service lock.
    with service._lock:
        assert not Path(grant.path).exists()
    assert put(url) == 404


@pytest.mark.parametrize("action", ["revoke", "close", "expire"])
def test_active_upload_cancellation_unblocks_socket_and_cleans_up(service, tmp_path, action):
    token, url, grant = reserve(service, tmp_path)
    peer = partial_upload(url)
    try:
        wait_claimed(grant)
        if action == "revoke":
            service.revoke(token)
        elif action == "close":
            service.close()
        else:
            grant.expires = time.monotonic() - 1
            service._expire()
        assert grant.completion.done()
        assert grant.file.closed
        assert not Path(grant.path).exists()
        assert not service._uploads
        assert peer.recv(1) == b""
    finally:
        peer.close()


def test_large_upload_has_bounded_python_memory(service, tmp_path):
    _, url, grant = reserve(service, tmp_path)
    address = urlsplit(url)
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=10)
    block = bytes(range(256)) * 256
    count = 512  # 32 MiB, sent without building a payload-sized Python object.
    expected = hashlib.sha256()
    tracemalloc.start()
    try:
        connection.putrequest("PUT", address.path)
        for key, value in {"Content-Length": str(len(block) * count),
                           "Content-Type": "image/png", "X-FoxMCP-Request-Id": "capture"}.items():
            connection.putheader(key, value)
        connection.endheaders()
        for _ in range(count):
            connection.send(block)
            expected.update(block)
        response = connection.getresponse()
        assert response.status == 204
        response.read()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        connection.close()
    assert peak < 4 * 1024 * 1024, peak
    actual = hashlib.sha256()
    with open(grant.completion.result()["path"], "rb") as image:
        while chunk := image.read(65536):
            actual.update(chunk)
    assert actual.digest() == expected.digest()


class ScreenshotPeer:
    def __init__(self, service, behavior="success"):
        self.service, self.behavior = service, behavior
        self.received = asyncio.Event()
        self.image = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 5000

    async def send_request_and_wait(self, request, timeout):
        self.request = request
        self.received.set()
        upload = request["data"]["upload"]
        if self.behavior == "hold":
            await asyncio.Event().wait()
        if self.behavior == "disconnect":
            return {"error": "Browser extension disconnected"}
        assert await asyncio.to_thread(put, upload["url"], self.image, upload["requestId"]) == 204
        if self.behavior == "error":
            return {"type": "error", "data": {"message": "capture failed after upload"}}
        return {"type": "response", "data": {
            "format": "png", "quality": 90, "tabId": 4,
            "upload": {"requestId": upload["requestId"],
                       "size": len(self.image) + (self.behavior == "wrong-size"),
                       "type": "image/png"}}}


async def screenshot_tool(service, peer):
    tools = FoxMCPTools(peer, file_transfers=service)
    return (await tools.mcp.get_tool("tabs_capture_screenshot")).fn


@pytest.mark.asyncio
async def test_tool_atomically_saves_uploaded_bytes_and_preserves_preview(service, tmp_path):
    peer = ScreenshotPeer(service)
    call = await screenshot_tool(service, peer)
    destination = tmp_path / "capture"
    destination.with_suffix('.png').write_bytes(b"previous image")
    result = await call(profile_id=2, tab_id=4, filename=str(destination))
    assert result.startswith("Screenshot saved to"), result
    assert destination.with_suffix('.png').read_bytes() == peer.image
    assert str(tmp_path) not in str(peer.request)
    assert not service._uploads
    preview = await call(profile_id=2, tab_id=4)
    assert ("data:image/png;base64," + base64.b64encode(peer.image).decode())[:100] in preview
    assert f"Base64 data size: {4 * ((len(peer.image) + 2) // 3)} characters" in preview
    assert not list(tmp_path.glob('.foxmcp-upload-*'))


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["error", "wrong-size", "disconnect"])
async def test_failed_control_reply_keeps_existing_destination(service, tmp_path, behavior):
    peer = ScreenshotPeer(service, behavior)
    call = await screenshot_tool(service, peer)
    path = tmp_path / "existing.png"
    path.write_bytes(b"existing")
    result = await call(profile_id=1, tab_id=4, filename=str(path))
    assert "saved to" not in result, result
    assert path.read_bytes() == b"existing"
    assert not service._uploads
    assert not list(tmp_path.glob('.foxmcp-upload-*'))


@pytest.mark.asyncio
async def test_cancelled_tool_revokes_grant_before_browser_response(service, tmp_path):
    peer = ScreenshotPeer(service, "hold")
    call = await screenshot_tool(service, peer)
    task = asyncio.create_task(call(profile_id=1, tab_id=4, filename=str(tmp_path / "cancel.png")))
    await peer.received.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not service._uploads
    assert not list(tmp_path.iterdir())
    assert put(peer.request["data"]["upload"]["url"]) == 404


@pytest.mark.asyncio
async def test_unfinished_upload_times_out_without_publishing(service, tmp_path):
    original_reserve = service.reserve_upload

    def short_grant(*args, **kwargs):
        return original_reserve(*args, **kwargs, timeout=.05)

    service.reserve_upload = short_grant

    class MissingUpload:
        async def send_request_and_wait(self, request, timeout):
            return {"type": "response", "data": {"format": "png", "upload": {
                "requestId": request["data"]["upload"]["requestId"],
                "type": "image/png", "size": 5}}}

    call = await screenshot_tool(service, MissingUpload())
    result = await call(profile_id=1, filename=str(tmp_path / 'missing.png'))
    assert result.startswith('Error capturing screenshot:'), result
    assert not service._uploads
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_cancel_after_http_upload_before_control_reply_cleans_staging(service, tmp_path):
    class HoldingReply(ScreenshotPeer):
        async def send_request_and_wait(self, request, timeout):
            self.request = request
            upload = request['data']['upload']
            status = await asyncio.to_thread(put, upload['url'], self.image, upload['requestId'])
            assert status == 204
            self.received.set()
            await asyncio.Event().wait()

    peer = HoldingReply(service)
    call = await screenshot_tool(service, peer)
    task = asyncio.create_task(call(profile_id=1, filename=str(tmp_path / 'pending.png')))
    await peer.received.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not service._uploads
    assert not list(tmp_path.iterdir())


def test_disk_error_during_discard_still_removes_staging(service, tmp_path):
    token, _, grant = reserve(service, tmp_path)
    handle = grant.file

    class FailedFlush:
        def close(self):
            handle.close()
            raise OSError('simulated disk full while flushing')

    grant.file = FailedFlush()
    service.revoke(token)
    assert handle.closed
    assert grant.completion.cancelled()
    assert not Path(grant.path).exists()
    assert not service._uploads


@pytest.mark.asyncio
@pytest.mark.parametrize('upload_completed', [False, True])
async def test_legacy_data_url_reply_is_refused(service, tmp_path, upload_completed):
    class LegacyPeer(ScreenshotPeer):
        async def send_request_and_wait(self, request, timeout):
            if upload_completed:
                await super().send_request_and_wait(request, timeout)
            return {'type': 'response', 'data': {
                'format': 'png', 'dataUrl': 'data:image/png;base64,aW1hZ2U='}}

    call = await screenshot_tool(service, LegacyPeer(service))
    output = tmp_path / 'existing.png'
    output.write_bytes(b'existing image')
    result = await call(profile_id=1, filename=str(output))
    assert 'missing or mismatched upload acknowledgement' in result
    assert output.read_bytes() == b'existing image'
    assert not service._uploads
    assert not list(tmp_path.glob('.foxmcp-upload-*'))


@pytest.mark.asyncio
async def test_screenshot_requires_a_transfer_service():
    class UnusedPeer:
        async def send_request_and_wait(self, request, timeout):
            pytest.fail('Screenshot cannot proceed without an upload service')

    tool = await FoxMCPTools(UnusedPeer()).mcp.get_tool('tabs_capture_screenshot')
    assert 'transfer service is unavailable' in await tool.fn(profile_id=1)


@pytest.mark.asyncio
@pytest.mark.parametrize('timeout_type', [asyncio.TimeoutError, TimeoutError],
                         ids=['asyncio-deadline', 'receiver-deadline'])
async def test_both_upload_timeout_types_return_capture_errors(service, tmp_path, timeout_type):
    original_reserve = service.reserve_upload

    def failed_upload(*args, **kwargs):
        token, url, grant = original_reserve(*args, **kwargs)
        grant.completion.set_exception(timeout_type('Upload deadline expired'))
        return token, url, grant

    service.reserve_upload = failed_upload

    class DeadlinePeer:
        async def send_request_and_wait(self, request, timeout):
            return {'type': 'response', 'data': {'upload': {
                'requestId': request['data']['upload']['requestId'],
                'type': 'image/png', 'size': 5}}}

    call = await screenshot_tool(service, DeadlinePeer())
    output = tmp_path / 'existing.png'
    output.write_bytes(b'existing image')
    result = await call(profile_id=1, filename=str(output))
    assert result == 'Error capturing screenshot: Upload deadline expired'
    assert output.read_bytes() == b'existing image'
    assert not service._uploads
    assert not list(tmp_path.glob('.foxmcp-upload-*'))
