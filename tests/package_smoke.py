"""Install final archives and exercise every tool over HTTP and stdio MCP.

Run with the project venv and --packages dist/packages. Creates a clean install
and a separate dependency venv through the actual installer. No model is used.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from email import policy
from email.parser import BytesParser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from unittest.mock import patch

import test_imports
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
import firefox_test_utils
from firefox_test_utils import FirefoxTestManager, resolve_firefox_path


ROOT = Path(__file__).resolve().parents[1]
PAGE = b'''<!doctype html><title>Release upload test</title>
<form><input id="file" name="file" type="file" required>
<input id="changes" name="changes" type="hidden" value="0"><button>Upload</button></form>
<button id="fetch" type="button">Fetch JSON</button>
<pre id="result">Waiting</pre><script>
document.querySelector('#fetch').addEventListener('click', async () => {
 const response = await fetch(document.body.dataset.apiUrl, {cache:'no-store'});
 document.body.dataset.apiResponse = JSON.stringify(await response.json());
});
document.querySelector('#file').addEventListener('change', () => {
 document.querySelector('#changes').value++;
});
document.querySelector('form').addEventListener('submit', async event => {
 event.preventDefault();
 const response = await fetch('/upload', {method:'POST', body:new FormData(event.target)});
 document.querySelector('#result').textContent = await response.text();
});</script>'''


def text(result):
    assert not result.is_error, result
    return '\n'.join(block.text for block in result.content if block.type == "text")


class SmokeClient:
    """Keep per-transport evidence, including the last call if a check fails."""

    def __init__(self, client, work, transport):
        self.client = client
        self.profile_id = None
        self.work = work
        self.transport = transport
        self.report = {"transport": transport, "passed": False, "checks": [], "calls": []}
        self.save()

    def save(self):
        (self.work / f"smoke-{self.transport}.json").write_text(json.dumps(self.report, indent=2))

    def checked(self, feature):
        self.report["checks"].append(feature)
        self.save()

    async def list_tools(self):
        return await self.client.list_tools()

    async def call_tool(self, name, arguments=None):
        arguments = dict(arguments or {})
        if name not in ("profiles_list", "debug_websocket_status") and "profile_id" not in arguments:
            if self.profile_id is None:
                discovery = await self.call_tool("profiles_list", {"populate": False})
                profiles = json.loads(text(discovery))["profiles"]
                assert len(profiles) <= 1, "Smoke test must explicitly select among multiple profiles"
                if profiles:
                    self.profile_id = profiles[0]["profile_id"]
            arguments["profile_id"] = self.profile_id or "unavailable-smoke-profile"
        call = {"tool": name, "arguments": arguments}
        self.report["calls"].append(call)
        self.save()
        try:
            result = await self.client.call_tool(name, arguments or {})
            call["result"] = text(result)[:5000]
            return result
        except Exception as error:
            call["error"] = str(error)
            raise
        finally:
            self.save()


async def call(client, tool_name, **arguments):
    return text(await client.call_tool(tool_name, arguments))


async def script_value(client, tab_id, expression):
    result = await call(client, "content_execute_script", tab_id=tab_id,
                        code=f"JSON.stringify({expression})")
    return json.loads(result.split("\n", 1)[1])


async def wait_page(client, tab_id, expected_url):
    for _ in range(100):
        result = await call(client, "content_execute_script", tab_id=tab_id,
                            code="JSON.stringify(document.readyState === 'complete' && "
                                 f"location.href === {json.dumps(expected_url)} && "
                                 "Boolean(document.querySelector('#file')))")
        if result.partition("\n")[2].strip() == "true":
            return
        await asyncio.sleep(.1)
    raise AssertionError(f"Tab {tab_id} did not finish loading {expected_url}")


def matched(pattern, result):
    match = re.search(pattern, result)
    assert match, result
    return match[1]


async def browser_features(client, url, cookie_store_id):
    for _ in range(120):
        status = await call(client, "debug_websocket_status")
        if status.startswith("Browser extension connected"):
            break
        await asyncio.sleep(.25)
    else:
        raise AssertionError("Packaged extension did not connect")
    client.checked("debug")
    flow = client.transport
    first_url = url + f"/page?case={flow}-first"
    second_url = url + f"/page?case={flow}-second"
    window_id = None
    folders = []
    bookmark_id = None
    monitor_id = None
    try:
        window_id = int(matched(r"ID (\d+)", await call(
            client, "create_window", url=url + "/page", width=900, height=700)))
        assert re.search(rf"- ID {window_id}:", await call(client, "list_windows"))
        assert f"Window {window_id}:" in await call(client, "get_window", window_id=window_id)
        assert "focused successfully" in await call(client, "focus_window", window_id=window_id)
        assert f"ID {window_id}" in await call(client, "get_current_window")
        assert "Updated window" in await call(client, "update_window", window_id=window_id,
                                               width=920, height=720)
        assert "920x720" in await call(client, "get_window", window_id=window_id)
        client.checked("windows")

        tab_id = int(matched(r"ID (\d+)", await call(
            client, "tabs_create", url=first_url, window_id=window_id, cookie_store_id=cookie_store_id)))
        other_id = int(matched(r"ID (\d+)", await call(
            client, "tabs_create", url=second_url, window_id=window_id, cookie_store_id=cookie_store_id)))
        assert "CONTAINER_IN_USE" in await call(client, "containers_remove", cookie_store_id=cookie_store_id)
        assert f"[cookie store {cookie_store_id}]" in await call(client, "tabs_list", cookie_store_id=cookie_store_id)
        await wait_page(client, tab_id, first_url)
        await wait_page(client, other_id, second_url)
        assert "Successfully switched" in await call(client, "tabs_switch", tab_id=tab_id)
        listing = await call(client, "tabs_list", window_id=window_id)
        assert any(f"ID {tab_id}:" in line and "(active)" in line for line in listing.splitlines())
        assert "Moved 1 of 1" in await call(client, "tabs_move", tab_ids=[other_id], index=0)
        listing = await call(client, "tabs_list", window_id=window_id)
        assert any(f"ID {other_id}:" in line and "index 0]" in line for line in listing.splitlines())
        group_id = int(matched(r"group (\d+)", await call(
            client, "tabs_group", tab_ids=[tab_id, other_id], title="Release smoke", color="blue")))
        assert "Updated group" in await call(client, "tabs_groups_update", group_id=group_id,
                                              title="Release updated", color="green", collapsed=False)
        groups = await call(client, "tabs_groups_query", window_id=window_id, title="Release updated")
        assert f"ID {group_id}: Release updated - green" in groups
        assert "Ungrouped 2" in await call(client, "tabs_ungroup", tab_ids=[tab_id, other_id])
        assert "No tab groups found" == await call(client, "tabs_groups_query", window_id=window_id)
        assert "Successfully closed" in await call(client, "tabs_close", tab_id=other_id)
        assert not re.search(rf"- ID {other_id}:", await call(client, "tabs_list", window_id=window_id))
        client.checked("tabs and tab groups")

        assert "Successfully navigated" in await call(client, "navigation_go_to_url", tab_id=tab_id,
                                                       url=second_url)
        await wait_page(client, tab_id, second_url)
        assert "Successfully navigated back" in await call(client, "navigation_back", params={"tab_id": tab_id})
        await wait_page(client, tab_id, first_url)
        assert "Successfully navigated forward" in await call(client, "navigation_forward", params={"tab_id": tab_id})
        await wait_page(client, tab_id, second_url)
        await script_value(client, tab_id, "(document.body.dataset.beforeReload = 'yes')")
        assert "Successfully reloaded" in await call(client, "navigation_reload", tab_id=tab_id, bypass_cache=True)
        for _ in range(100):
            await wait_page(client, tab_id, second_url)
            if await script_value(client, tab_id, "document.body.dataset.beforeReload === undefined"):
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError("Reload did not replace the document")
        assert '<form' in await call(client, "content_get_html", tab_id=tab_id)
        assert "Waiting" in await call(client, "content_get_text", tab_id=tab_id)
        client.checked("navigation and content")

        screenshot = client.work / f"smoke-{flow}.png"
        assert "Screenshot saved" in await call(client, "tabs_capture_screenshot",
                                                 filename=str(screenshot), window_id=window_id)
        assert screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert screenshot.stat().st_size > 100
        client.checked("screenshots")

        for _ in range(100):
            history = await call(client, "history_query", query=first_url)
            if history.startswith("Found ") and first_url in history:
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError("Visited page never appeared in history")
        assert second_url in await call(client, "history_get_recent", count=50)
        assert "Successfully deleted" in await call(client, "history_delete_item", url=first_url)
        assert (await call(client, "history_query", query=first_url)).startswith("No history items found")
        client.checked("history")

        for title in (f"Release {flow} source", f"Release {flow} destination"):
            folders.append(matched(r"ID: ([^)]+)", await call(client, "bookmarks_create_folder", title=title)))
        title = f"Release {flow} bookmark"
        bookmark_id = matched(r"ID: ([^)]+)", await call(
            client, "bookmarks_create", title=title, url=first_url, parent_id=folders[0]))
        assert f"ID: {bookmark_id}," in await call(client, "bookmarks_list", folder_id=folders[0])
        assert "Updated bookmark" in await call(client, "bookmarks_update", bookmark_id=bookmark_id,
                                                  title=title + " updated", url=second_url)
        found = await call(client, "bookmarks_search", query=title + " updated")
        assert bookmark_id in found and second_url in found
        assert "Moved " in await call(client, "bookmarks_move", bookmark_id=bookmark_id,
                                                parent_id=folders[1], index=0)
        assert await call(client, "bookmarks_list", folder_id=folders[0]) == "No bookmarks found"
        moved = await call(client, "bookmarks_list", folder_id=folders[1])
        assert f"ID: {bookmark_id}, Parent: {folders[1]}, Index: 0" in moved
        assert "Successfully deleted" in await call(client, "bookmarks_delete", bookmark_id=bookmark_id)
        bookmark_id = None
        assert (await call(client, "bookmarks_search", query=title)).startswith("No bookmarks found")
        client.checked("bookmarks")

        api_url = url + f"/api?flow={flow}"
        started = json.loads(await call(client, "requests_start_monitoring", url_patterns=[api_url],
                                        tab_id=tab_id, options={"capture_response_bodies": True,
                                        "content_types_to_capture": ["application/json"]}))
        monitor_id = started["monitor_id"]
        await call(client, "content_execute_script", tab_id=tab_id,
                   code="document.body.dataset.apiUrl = " + json.dumps(api_url)
                        + "; document.querySelector('#fetch').click(); 'fetch requested'")
        for _ in range(100):
            fetched = await script_value(client, tab_id,
                "JSON.parse(document.body.dataset.apiResponse || 'null')")
            if fetched == {"release": flow}:
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError("Page button did not fetch the fixture JSON")
        for _ in range(100):
            captured = json.loads(await call(client, "requests_list_captured", monitor_id=monitor_id))
            requests = [request for request in captured["requests"] if request["url"] == api_url]
            if requests:
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError("Fixture fetch was not captured")
        assert len(requests) == 1 and requests[0]["status_code"] == 200
        content = json.loads(await call(client, "requests_get_content", monitor_id=monitor_id,
                                        request_id=requests[0]["request_id"]))
        assert content["response_body"]["included"], content
        assert json.loads(content["response_body"]["content"]) == {"release": flow}
        stopped = json.loads(await call(client, "requests_stop_monitoring", monitor_id=monitor_id))
        assert stopped["status"] == "stopped" and stopped["total_requests_captured"] == 1
        monitor_id = None
        client.checked("request capture and response body")
    finally:
        if monitor_id:
            await call(client, "requests_stop_monitoring", monitor_id=monitor_id)
        if bookmark_id:
            await call(client, "bookmarks_delete", bookmark_id=bookmark_id)
        for folder in reversed(folders):
            assert "Successfully deleted" in await call(client, "bookmarks_delete", bookmark_id=folder)
        if window_id is not None:
            assert "closed successfully" in await call(client, "close_window", window_id=window_id)
            assert not re.search(rf"- ID {window_id}:", await call(client, "list_windows"))
        for visited in (first_url, second_url):
            await call(client, "history_delete_item", url=visited)


async def exercise(client, url, source, work, transport, receipts):
    recorded = SmokeClient(client, work, transport)
    store = None
    try:
        # Match browser_features' initial connection wait before calling new APIs.
        for _ in range(120):
            if (await call(recorded, "debug_websocket_status")).startswith("Browser extension connected"):
                break
            await asyncio.sleep(.25)
        discovery = json.loads(await call(recorded, "containers_list"))
        assert discovery["default_cookie_store_id"] == "firefox-default", discovery
        created = json.loads(await call(recorded, "containers_create", name="Package test"))["container"]
        store = created["cookie_store_id"]
        updated = json.loads(await call(recorded, "containers_update", cookie_store_id=store,
                                       name="Package updated", color="red"))["container"]
        assert updated["cookie_store_id"] == store and updated["name"] == "Package updated"
        await browser_features(recorded, url, store)
        before_upload = len(receipts)
        await upload(recorded, url, source, store)
        expected = {"name": source.name, "type": "application/x-foxmcp-release-test",
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "changes": 1}
        assert len(receipts) == before_upload + 1 and receipts[-1] == expected, receipts
        recorded.checked("file upload, exact bytes and handle release")
        assert json.loads(await call(recorded, "containers_remove", cookie_store_id=store))["removed"]
        store = None
        recorded.checked("container discovery, lifecycle and tab selection")
        names = {tool.name for tool in await client.list_tools()}
        assert len(names) == 46, names
        called = {call["tool"] for call in recorded.report["calls"]}
        assert not names - called, f"Tools missing package smoke coverage: {sorted(names - called)}"
        recorded.report["passed"] = True
        print(f"PASS {transport}: all {len(names)} advertised tools exercised", flush=True)
    except Exception as error:
        recorded.report["error"] = str(error)
        raise
    finally:
        if store is not None:
            await call(recorded, "containers_remove", cookie_store_id=store)
        recorded.save()


async def upload(client, url, source, cookie_store_id):
    names = {tool.name for tool in await client.list_tools()}
    assert {"content_load_file", "content_execute_script", "tabs_create"} <= names
    for _ in range(120):
        status = text(await client.call_tool("tabs_list", {}))
        if "No extension connection" not in status:
            break
        await asyncio.sleep(.25)
    else:
        raise AssertionError("Packaged extension did not connect")
    created = text(await client.call_tool("tabs_create", {"url": url + "/page", "cookie_store_id": cookie_store_id}))
    match = re.search(r"ID (\d+)", created)
    assert match, created
    tab_id = int(match[1])
    try:
        for _ in range(100):
            ready = text(await client.call_tool("content_execute_script", {
                "tab_id": tab_id, "code": "Boolean(document.querySelector('#file'))"}))
            if "True" in ready or "true" in ready:
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError("Upload fixture did not load")
        loaded = json.loads(text(await client.call_tool("content_load_file", {
            "tab_id": tab_id, "path": str(source), "mime_type": "application/x-foxmcp-release-test"})))
        assert loaded["name"] == source.name
        assert loaded["size"] == source.stat().st_size
        assigned = text(await client.call_tool("content_execute_predefined", {
            "tab_id": tab_id, "script_name": "set-file-input.py",
            "script_args": json.dumps([loaded["file_id"], "#file"])}))
        assert source.name in assigned, assigned
        submitted = text(await client.call_tool("content_execute_script", {
            "tab_id": tab_id,
            "code": "(() => { if (globalThis.foxmcpFiles.size !== 0) "
                    "throw new Error('File handle was not released');"
                    "document.querySelector('form').requestSubmit();"
                    "return 'submitted'; })()"}))
        assert "submitted" in submitted, submitted
        for _ in range(100):
            page = text(await client.call_tool("content_get_text", {"tab_id": tab_id}))
            if "Uploaded " + source.name in page:
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError("Upload completion was not displayed")
    finally:
        await client.call_tool("tabs_close", {"tab_id": tab_id})


async def smoke(packages, work):
    assets = work / "assets"
    assets.mkdir()
    for name in ("foxmcp-server.zip", "foxmcp@codemud.org.xpi", "SHA256SUMS"):
        shutil.copy2(packages / name, assets / name)
    shutil.copytree(ROOT / "scripts", assets / "scripts")
    shutil.copytree(ROOT / "predefined-ex", assets / "predefined-ex")
    receipts = []

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api":
                body = json.dumps({"release": parse_qs(parsed.query)["flow"][0]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path != "/page":
                return super().do_GET()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def do_POST(self):
            size = int(self.headers.get("Content-Length", "0"))
            if self.path != "/upload" or not 0 < size < 1024 * 1024:
                self.send_error(400)
                return
            headers = f"Content-Type: {self.headers['Content-Type']}\r\nMIME-Version: 1.0\r\n\r\n"
            message = BytesParser(policy=policy.default).parsebytes(headers.encode() + self.rfile.read(size))
            fields = {part.get_param("name", header="content-disposition"): part
                      for part in message.iter_parts()}
            file = fields["file"]
            body = file.get_payload(decode=True)
            receipts.append({"name": file.get_filename(), "type": file.get_content_type(),
                             "sha256": hashlib.sha256(body).hexdigest(),
                             "changes": int(fields["changes"].get_content())})
            response = ("Uploaded " + file.get_filename()).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    website = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(assets)))
    thread = threading.Thread(target=website.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{website.server_port}"
    install = work / "installed"
    install.mkdir()
    env = dict(os.environ, FOXMCP_RELEASE_URL=url, FOXMCP_SOURCE_URL=url)
    for key in ("PYTHONPATH", "FOXMCP_DISABLE_TOOLS", "FOXMCP_ENABLE_TOOLS"):
        env.pop(key, None)
    firefox = FirefoxTestManager(firefox_path=resolve_firefox_path(), test_port=31087)
    process = None
    try:
        with (work / "installer.log").open("w") as log:
            result = await asyncio.to_thread(subprocess.run,
                ["bash", str(ROOT / "scripts/install-from-github.sh"), "--non-interactive"],
                cwd=install, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        assert result.returncode == 0, (work / "installer.log").read_text()
        python = install / "venv/bin/python"
        script = install / "server/server.py"
        env["FOXMCP_EXT_SCRIPTS"] = str(install / "predefined-scripts")
        source = work / "release report.csv"
        source.write_bytes(b"quarter,revenue\nQ1,1200\nQ2,2300\n")
        def start_browser():
            # Start only after the transport is ready: the shared test profile
            # has a finite reconnect budget. Use a fresh browser for each mode.
            with patch.object(firefox_test_utils, "_get_extension_xpi_path",
                              return_value=str(assets / "foxmcp@codemud.org.xpi")):
                assert firefox.setup_and_start_firefox(headless=True, skip_on_failure=False)
        with (work / "http-server.log").open("w") as log:
            process = await asyncio.create_subprocess_exec(
                str(python), str(script), "--port", "31087", "--mcp-port", "31086",
                cwd=install, env=env, stdout=log, stderr=log)
            for _ in range(120):
                assert process.returncode is None, "Packaged server exited during startup"
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", 31086)
                    writer.close()
                    await writer.wait_closed()
                    break
                except OSError:
                    await asyncio.sleep(.25)
            else:
                raise AssertionError("Packaged HTTP server did not start")
            start_browser()
            async with Client("http://127.0.0.1:31086/mcp") as client:
                await exercise(client, url, source, work, "http", receipts)
            firefox.cleanup()
            process.terminate()
            await asyncio.wait_for(process.wait(), 15)
            process = None
        transport = PythonStdioTransport(script_path=script, python_cmd=str(python),
                                        args=["--stdio", "--port", "31087"],
                                        cwd=str(install), env={**env, "PYTHONPATH": ""},
                                        log_file=work / "stdio-server.log")
        async with Client(transport) as client:
            start_browser()
            await exercise(client, url, source, work, "stdio", receipts)
        expected = {"name": source.name, "type": "application/x-foxmcp-release-test",
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "changes": 1}
        assert receipts == [expected, expected], receipts
        (work / "receipts.json").write_text(json.dumps(receipts, indent=2))
        print("PASS: clean installer + all packaged tools over HTTP and stdio; upload bytes and events verified")
    finally:
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 15)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        firefox.cleanup()
        website.shutdown()
        website.server_close()
        thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="foxmcp-package-smoke-"))
    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"Package smoke artifacts: {work_dir}", flush=True)
    asyncio.run(asyncio.wait_for(smoke(args.packages.resolve(), work_dir.resolve()), 360))
