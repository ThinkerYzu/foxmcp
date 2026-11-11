"""Capture filters and redirected requests through actual MCP calls and local Firefox."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from threading import Thread
from types import SimpleNamespace
import uuid

from fastmcp import Client
import pytest
import pytest_asyncio

import test_imports  # noqa: F401


@pytest.fixture
def redirect_site():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.do_GET()

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/page":
                body = b'''<!doctype html><title>Capture fixture</title>
<button id="fetch">Fetch</button><pre id="result"></pre><script>
document.querySelector('#fetch').onclick=async function(){
  try {
    const r=await fetch(this.dataset.path, {method:this.dataset.method,
      body:this.dataset.method==='POST'?'secret=42':undefined});
    document.querySelector('#result').textContent=await r.text();
  } catch(e) { document.querySelector('#result').textContent='failed'; }
};</script>'''
                status, mime = 200, "text/html"
            elif path.startswith("/redirect/") or path == "/loop":
                if path == "/loop":
                    status, target = 302, "/loop"
                else:
                    _, _, code, remaining = path.split("/")
                    status = int(code)
                    target = (f"/redirect/{code}/{int(remaining) - 1}"
                              if int(remaining) > 1 else "/final")
                    if "broken" in self.path:
                        target = "/broken"
                self.send_response(status)
                self.send_header("Location", target)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            elif path == "/broken":
                self.close_connection = True
                return
            else:
                body = b"done"
                status, mime = (500 if path == "/fail" else 200), "text/plain"
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    site = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=site.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{site.server_port}"
    finally:
        site.shutdown()
        site.server_close()
        thread.join(timeout=5)


@pytest_asyncio.fixture
async def capture_browser(server_with_extension, redirect_site):
    setup = server_with_extension
    profile_id = next(iter(setup["server"].profiles))
    monitors = []
    tab_id = None
    async with Client(f"http://localhost:{setup['mcp_port']}/mcp/") as client:
        async def call(name, **args):
            result = await client.call_tool(name, {"profile_id": profile_id, **args})
            assert not result.is_error, result
            return result.content[0].text

        async def start(pattern="/*", **options):
            result = json.loads(await call("requests_start_monitoring", tab_id=tab_id,
                url_patterns=[redirect_site + pattern], options=options))
            assert result["status"] == "active", result
            monitor = result["monitor_id"]
            assert monitor not in monitors
            monitors.append(monitor)
            return monitor

        async def stop(monitor):
            await call("requests_stop_monitoring", monitor_id=monitor)
            monitors.remove(monitor)

        async def listed(monitor, **args):
            return json.loads(await call("requests_list_captured", monitor_id=monitor, **args))

        async def fetch(path, method="GET"):
            await call("content_execute_script", tab_id=tab_id, code=
                "document.querySelector('#result').textContent='';"
                f"document.querySelector('#fetch').dataset.path={json.dumps(path)};"
                f"document.querySelector('#fetch').dataset.method={json.dumps(method)};"
                "document.querySelector('#fetch').click();'started'")
            for _ in range(100):
                result = await call("content_execute_script", tab_id=tab_id,
                    code="document.querySelector('#result').textContent")
                if result.endswith("done") or result.endswith("failed"):
                    return result
                await asyncio.sleep(.1)
            pytest.fail(f"Fetch did not finish: {result}")

        async def wait_count(monitor, count):
            for _ in range(100):
                result = await listed(monitor)
                if result["total_requests"] >= count:
                    assert result["total_requests"] == count, result
                    return result["requests"]
                await asyncio.sleep(.1)
            pytest.fail(f"Capture did not finish: {result}")

        try:
            tab_id = int(re.search(r"ID (\d+)", await call("tabs_create",
                url=redirect_site + "/page", active=False))[1])
            for _ in range(100):
                if (await call("content_execute_script", tab_id=tab_id,
                        code="document.querySelector('#fetch') ? 'ready' : 'loading'")).endswith("ready"):
                    break
                await asyncio.sleep(.1)
            else:
                pytest.fail("Fixture did not load")
            yield SimpleNamespace(call=call, start=start, stop=stop, listed=listed,
                                  fetch=fetch, wait_count=wait_count, site=redirect_site,
                                  server=setup["server"], profile_id=profile_id)
        finally:
            for monitor in monitors[:]:
                await stop(monitor)
            if tab_id is not None:
                await call("tabs_close", tab_id=tab_id)


@pytest.mark.asyncio
async def test_capture_filters_and_limit_in_firefox(capture_browser):
    b = capture_browser
    broad = await b.start()
    post = await b.start(methods=["post"])
    xhr = await b.start(resource_types=["xmlhttprequest"])
    script = await b.start(resource_types=["script"])
    failed = await b.start(failed_only=True)
    minimum = await b.start(min_status=400)
    combined = await b.start(methods=["POST"], min_status=400)
    for path, method in (("/ok", "GET"), ("/ok", "POST"),
                         ("/fail", "GET"), ("/fail", "POST")):
        assert (await b.fetch(path, method)).endswith("done")
    for entry in await b.wait_count(broad, 4):
        assert entry["redirects"] == [] and "hops" not in entry
        assert entry["initial_status_code"] == entry["status_code"]
        assert "initial_redirect_url" not in entry
    assert len(await b.wait_count(post, 2)) == 2
    assert len(await b.wait_count(xhr, 4)) == 4
    assert (await b.listed(script))["requests"] == []
    assert all(r["status_code"] == 500 for r in await b.wait_count(failed, 2))
    assert all(r["status_code"] == 500 for r in await b.wait_count(minimum, 2))
    assert (await b.wait_count(combined, 1))[0]["method"] == "POST"
    limited = await b.listed(broad, limit=2)
    assert limited["total_requests"] == 4 and limited["returned_requests"] == 2
    assert all(r["status_code"] == 500 for r in limited["requests"])
    for options in ({"methods": "GET"}, {"resource_types": [""]},
                    {"min_status": True}, {"failed_only": 1}):
        result = await b.server.send_request_and_wait({
            "id": str(uuid.uuid4()), "type": "request", "profile_id": b.profile_id,
            "action": "requests.start_monitoring", "data": {"options": options}})
        assert result["type"] == "error", result
        assert result["data"]["code"] == "INVALID_PARAMETER", result


@pytest.mark.asyncio
async def test_redirects_and_monitor_independence(capture_browser):
    b = capture_browser
    # First reproduce the review scenario with no other monitor to record POST.
    get = await b.start(methods=["GET"])
    await b.fetch("/redirect/302/2", "POST")
    assert (await b.listed(get))["requests"] == []
    await b.stop(get)

    post_alone = await b.start(methods=["POST"])
    await b.fetch("/redirect/302/2", "POST")
    solo_entry = (await b.wait_count(post_alone, 1))[0]
    assert solo_entry["method"] == "POST" and solo_entry["initial_status_code"] == 302
    assert [r["method"] for r in solo_entry["redirects"]] == ["GET", "GET"]
    await b.stop(post_alone)

    broad = await b.start()
    get = await b.start(methods=["GET"])
    post = await b.start(methods=["post"])
    initial_url = await b.start(pattern="/redirect/*")
    final_url = await b.start(pattern="/final")
    failed = await b.start(failed_only=True)
    for count, (code, depth) in enumerate(((302, 1), (302, 2), (303, 3), (307, 2), (308, 2)), 1):
        path = f"/redirect/{code}/{depth}"
        assert (await b.fetch(path, "POST")).endswith("done")
        entry = (await b.wait_count(broad, count))[-1]
        assert entry["url"] == b.site + path and entry["method"] == "POST"
        assert entry["status_code"] == 200
        redirects = entry["redirects"]
        assert "hops" not in entry and len(redirects) == depth
        assert entry["initial_status_code"] == code
        assert entry["initial_redirect_url"] == redirects[0]["url"]
        expected_methods = ["GET"] * depth if code in (302, 303) else ["POST"] * depth
        assert [r["method"] for r in redirects] == expected_methods
        assert [r["url"] for r in redirects] == [
            b.site + f"/redirect/{code}/{n}" for n in range(depth - 1, 0, -1)] + [b.site + "/final"]
        assert [r["status_code"] for r in redirects] == [code] * (depth - 1) + [200]
        assert [r["redirect_url"] for r in redirects[:-1]] == [r["url"] for r in redirects[1:]]
        assert (await b.wait_count(post, count))[-1]["redirects"] == redirects
        assert (await b.wait_count(initial_url, count))[-1]["redirects"] == redirects
        for _ in range(100):
            content = json.loads(await b.call("requests_get_content", monitor_id=post,
                request_id=entry["request_id"]))
            if content["response_body"]["included"]:
                break
            await asyncio.sleep(.1)
        assert content["response_body"]["content"] == "done", content
        assert content["redirects"] == redirects and "hops" not in content
        assert content["url"] == entry["url"] and content["method"] == "POST"
        assert content["initial_status_code"] == code and content["status_code"] == 200
        assert content["initial_redirect_url"] == redirects[0]["url"]
    assert (await b.listed(get))["requests"] == []
    assert (await b.listed(final_url))["requests"] == []
    assert (await b.listed(failed))["requests"] == []
    await b.stop(post)
    assert len((await b.listed(post))["requests"]) == 5
    assert json.loads(await b.call("requests_get_content", monitor_id=post,
        request_id=entry["request_id"]))["redirects"] == redirects


@pytest.mark.asyncio
async def test_failed_redirect_chains(capture_browser):
    b = capture_browser
    broad = await b.start()
    failed = await b.start(failed_only=True)
    minimum = await b.start(min_status=400)
    for count, path in enumerate(("/redirect/302/1?broken", "/loop"), 1):
        assert (await b.fetch(path)).endswith("failed")
        entry = (await b.wait_count(broad, count))[-1]
        assert entry["error"], entry
        assert entry["url"] == b.site + path and entry["initial_status_code"] == 302
        assert entry["initial_redirect_url"] == entry["redirects"][0]["url"]
        assert entry["redirects"][-1]["error"] == entry["error"]
        if path == "/loop":
            assert len(entry["redirects"]) > 1
            assert all(r["url"] == b.site + "/loop" for r in entry["redirects"])
        else:
            assert len(entry["redirects"]) == 1
        assert (await b.wait_count(failed, count))[-1]["redirects"] == entry["redirects"]
    assert (await b.listed(minimum))["requests"] == []
