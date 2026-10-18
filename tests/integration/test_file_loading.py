"""Local files reach real Firefox without putting their bytes on the WebSocket."""

import asyncio
import hashlib
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import test_imports


@pytest.fixture
def upload_page():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            page = b'''<!doctype html><title>File upload fixture</title>
                <input type="file" id="upload"><script>
                window.inputEvents = [];
                for (const name of ['input', 'change']) {
                  document.querySelector('input').addEventListener(name, () => inputEvents.push(name));
                }
                </script>'''
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()
    server.server_close()
    thread.join()


async def browser_request(server, action, data, allow_loading=False):
    response = await server.send_request_and_wait({
        "id": str(uuid.uuid4()), "type": "request", "action": action, "data": data
    })
    if allow_loading and "Missing host permission for the tab" in response.get("data", {}).get("message", ""):
        return {"result": False}
    assert "error" not in response and response.get("type") == "response", response
    return response["data"]


async def open_fixture(server, url):
    tab = await browser_request(server, "tabs.create", {"url": url, "active": True})
    tab_id = tab["tab"]["id"]
    for _ in range(100):
        result = await browser_request(server, "content.execute_script", {
            "tabId": tab_id, "script": "document.readyState === 'complete' && !!document.querySelector('#upload')"
        }, allow_loading=True)
        if result.get("result"):
            return tab_id
        await asyncio.sleep(0.1)
    pytest.fail("Local upload fixture never loaded")


@pytest.mark.asyncio
async def test_load_file_then_assign_with_predefined_script(
    server_with_extension, upload_page, tmp_path, monkeypatch
):
    server = server_with_extension["server"]
    tab_id = await open_fixture(server, upload_page)
    source = tmp_path / 'résumé "2026".pdf'
    contents = bytes(range(256)) * 32769
    source.write_bytes(contents)
    tool = await server.mcp_tools.mcp.get_tool("content_load_file")
    script_tool = await server.mcp_tools.mcp.get_tool("content_execute_predefined")
    monkeypatch.setenv("FOXMCP_EXT_SCRIPTS", str(Path(__file__).resolve().parents[2] / "predefined-ex"))
    try:
        result = json.loads(await tool.fn(tab_id=tab_id, path=str(source), mime_type="application/x-foxmcp-test"))
        assert result["name"] == source.name
        assert result["size"] == len(contents)
        assert result["type"] == "application/x-foxmcp-test"
        assert str(tmp_path) not in json.dumps(result)
        assigned = await script_tool.fn(
            tab_id=tab_id, script_name="set-file-input.py",
            script_args=json.dumps([result["file_id"], "#upload"])
        )
        assert "Predefined script 'set-file-input.py' result" in assigned
        actual = await browser_request(server, "content.execute_script", {
            "tabId": tab_id, "script": '''(async () => {
              const input = document.querySelector('#upload').wrappedJSObject;
              const file = input.files[0];
              const bytes = await file.arrayBuffer();
              const hash = await crypto.subtle.digest('SHA-256', bytes);
              return {name: file.name, type: file.type, size: file.size, lastModified: file.lastModified,
                events: Array.from(window.wrappedJSObject.inputEvents), handles: globalThis.foxmcpFiles.size,
                sha256: Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('')};
            })()'''
        })
        assert actual["result"] == {
            "name": source.name, "type": "application/x-foxmcp-test", "size": len(contents),
            "lastModified": source.stat().st_mtime_ns // 1_000_000,
            "events": ["input", "change"], "handles": 0,
            "sha256": hashlib.sha256(contents).hexdigest()
        }
    finally:
        await browser_request(server, "tabs.close", {"tabId": tab_id})


@pytest.mark.asyncio
async def test_file_handle_is_tab_local_and_navigation_discards_it(
    server_with_extension, upload_page, tmp_path
):
    server = server_with_extension["server"]
    tab_id = await open_fixture(server, upload_page)
    other_id = await open_fixture(server, upload_page)
    source = tmp_path / "empty.txt"
    source.touch()
    try:
        tool = await server.mcp_tools.mcp.get_tool("content_load_file")
        result = json.loads(await tool.fn(tab_id=tab_id, path=str(source)))
        assert result["type"] == "text/plain" and result["size"] == 0
        file_id = json.dumps(result["file_id"])
        script = f"Boolean(globalThis.foxmcpFiles?.has({file_id}))"
        assert (await browser_request(server, "content.execute_script", {"tabId": tab_id, "script": script}))["result"]
        assert not (await browser_request(server, "content.execute_script", {"tabId": other_id, "script": script}))["result"]
        await browser_request(server, "navigation.go_to_url", {"tabId": tab_id, "url": upload_page + "?next"})
        for _ in range(100):
            state = await browser_request(server, "content.execute_script", {
                "tabId": tab_id,
                "script": "location.search === '?next' && document.readyState === 'complete'"
            }, allow_loading=True)
            if state.get("result"):
                break
            await asyncio.sleep(.1)
        else:
            pytest.fail("Fixture navigation never finished")
        assert not (await browser_request(server, "content.execute_script", {"tabId": tab_id, "script": script}))["result"]
        await browser_request(server, "content.execute_script", {
            "tabId": tab_id, "script": '''(() => {
              globalThis.foxmcpOriginalTimeout = globalThis.setTimeout;
              globalThis.setTimeout = (callback, delay, ...args) =>
                foxmcpOriginalTimeout.call(window, callback, delay === 300000 ? 1000 : delay, ...args);
              return true;
            })()'''
        })
        expiring = json.loads(await tool.fn(tab_id=tab_id, path=str(source)))
        await browser_request(server, "content.execute_script", {
            "tabId": tab_id, "script": "globalThis.setTimeout = foxmcpOriginalTimeout; true"
        })
        script = f"Boolean(globalThis.foxmcpFiles?.has({json.dumps(expiring['file_id'])}))"
        for _ in range(50):
            if not (await browser_request(server, "content.execute_script", {
                "tabId": tab_id, "script": script
            }))["result"]:
                break
            await asyncio.sleep(.1)
        else:
            pytest.fail("Unused file handle did not expire")
    finally:
        await browser_request(server, "tabs.close", {"tabId": tab_id})
        await browser_request(server, "tabs.close", {"tabId": other_id})


@pytest.mark.asyncio
async def test_navigation_during_transfer_rejects_delivery(
    server_with_extension, upload_page, tmp_path, monkeypatch
):
    server = server_with_extension["server"]
    tab_id = await open_fixture(server, upload_page)
    source = tmp_path / "slow.bin"
    source.write_bytes(b"x" * 1024)
    started = threading.Event()
    release = threading.Event()
    grant_file = server.file_transfers.grant

    class GatedFile:
        def __init__(self, file):
            self.file = file

        def read(self, size):
            started.set()
            assert release.wait(15), "Test did not release the transfer"
            return self.file.read(size)

        def close(self):
            self.file.close()

    def grant(*args, **kwargs):
        token, url, metadata = grant_file(*args, **kwargs)
        server.file_transfers._grants[token].file = GatedFile(server.file_transfers._grants[token].file)
        return token, url, metadata

    monkeypatch.setattr(server.file_transfers, "grant", grant)
    tool = await server.mcp_tools.mcp.get_tool("content_load_file")
    task = asyncio.create_task(tool.fn(tab_id=tab_id, path=str(source)))
    try:
        assert await asyncio.to_thread(started.wait, 10)
        await browser_request(server, "navigation.go_to_url", {"tabId": tab_id, "url": upload_page + "?during"})
        for _ in range(100):
            state = await browser_request(server, "content.execute_script", {
                "tabId": tab_id,
                "script": "location.search === '?during' && document.readyState === 'complete'"
            }, allow_loading=True)
            if state.get("result"):
                break
            await asyncio.sleep(.1)
        else:
            pytest.fail("Navigation during transfer never finished")
        release.set()
        assert "Failed to load file" in await task
        assert not (await browser_request(server, "content.execute_script", {
            "tabId": tab_id, "script": "Boolean(globalThis.foxmcpFiles?.size)"
        }))["result"]
    finally:
        release.set()
        await task
        await browser_request(server, "tabs.close", {"tabId": tab_id})
