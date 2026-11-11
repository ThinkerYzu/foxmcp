"""Verify capture policies against one real response shared by overlapping monitors."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from threading import Thread
import uuid

import pytest
from fastmcp import Client

import test_imports  # noqa: F401


BODY = "abcdefghij" * 12


@pytest.fixture
def capture_site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.reply(b'''<!doctype html><title>Monitor options fixture</title>
<button id="fetch">Fetch</button><pre id="result"></pre><script>
document.querySelector('#fetch').onclick = async function () {
  const response = await fetch('/body?' + this.dataset.suffix, {
    method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'secret=42'
  });
  document.querySelector('#result').textContent = await response.text();
};
</script>''', "text/html")

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.reply(BODY.encode(), "text/plain")

        def reply(self, data, content_type):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    website = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=website.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{website.server_port}"
    finally:
        website.shutdown()
        website.server_close()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_monitor_policies_are_independent_and_survive_stop(server_with_extension, capture_site):
    setup = server_with_extension
    server = setup["server"]
    profile_id = next(iter(server.profiles))
    monitors = []
    tab_id = None
    async with Client(f"http://localhost:{setup['mcp_port']}/mcp/") as client:
        async def call(name, **args):
            result = await client.call_tool(name, {"profile_id": profile_id, **args})
            assert not result.is_error, result
            return result.content[0].text

        async def request(action, data):
            return await server.send_request_and_wait({
                "id": str(uuid.uuid4()), "type": "request", "profile_id": profile_id,
                "action": action, "data": data})

        async def start(options, pattern=None):
            result = json.loads(await call("requests_start_monitoring", tab_id=tab_id,
                url_patterns=[pattern or capture_site + "/body*"], options=options))
            assert result["status"] == "active", result
            monitor_id = result["monitor_id"]
            assert monitor_id not in monitors
            monitors.append(monitor_id)
            return monitor_id

        async def fetch_body(suffix):
            script = ("document.querySelector('#result').textContent='';"
                      f"document.querySelector('#fetch').dataset.suffix={json.dumps(suffix)};"
                      "document.querySelector('#fetch').click(); 'started'")
            await call("content_execute_script", tab_id=tab_id, code=script)
            for _ in range(100):
                result = await call("content_execute_script", tab_id=tab_id,
                                    code="document.querySelector('#result').textContent")
                if result.partition("\n")[2] == BODY:
                    return  # Every byte still reached the page intact.
                await asyncio.sleep(.1)
            pytest.fail(f"Page did not receive the full response: {result}")

        async def content(monitor_id, suffix, wait_for_body=False):
            for _ in range(100):
                listing = json.loads(await call("requests_list_captured", monitor_id=monitor_id))
                matching = [item for item in listing.get("requests", []) if item["url"].endswith(suffix)]
                if matching:
                    result = json.loads(await call("requests_get_content", monitor_id=monitor_id,
                                                   request_id=matching[0]["request_id"]))
                    body = result["response_body"]
                    # Completion metadata can precede the response filter's onstop.
                    if body["size_bytes"] == len(BODY) and (not wait_for_body or body["included"]):
                        return matching[0]["request_id"], result
                await asyncio.sleep(.1)
            pytest.fail(f"Request/body not captured for {monitor_id}: {listing}")

        try:
            created = await call("tabs_create", url=capture_site, active=False)
            tab_id = int(re.search(r"ID (\d+)", created)[1])
            for _ in range(100):
                ready = await call("content_execute_script", tab_id=tab_id,
                                  code="document.readyState")
                if ready.endswith("complete"):
                    break
                await asyncio.sleep(.1)
            else:
                pytest.fail("Fixture page did not finish loading")

            for invalid in ({"max_body_size": 0}, {"max_body_size": -1},
                            {"capture_response_bodies": "false"},
                            {"capture_request_bodies": 0},
                            {"content_types_to_capture": "text/plain"},
                            {"content_types_to_capture": [""]},
                            {"sensitive_headers": ["Cookie"]}, {"unknown": True}):
                response = await request("requests.start_monitoring", {
                    "url_patterns": [capture_site + "/*"], "options": invalid})
                assert response["type"] == "error", response
                assert response["data"]["code"] == "INVALID_PARAMETER", response

            small = await start({"capture_request_bodies": False, "max_body_size": 4,
                                 "content_types_to_capture": ["text/plain"]})
            large = await start({"max_body_size": 40, "content_types_to_capture": ["text/plain"]})
            excluded = await start({"max_body_size": 10, "content_types_to_capture": ["application/json"]})
            disabled = await start({"capture_request_bodies": False, "capture_response_bodies": False})
            all_text = await start({"max_body_size": 80, "content_types_to_capture": []})
            await fetch_body("overlap")

            for monitor_id, limit in ((small, 4), (large, 40), (all_text, 80)):
                request_id, data = await content(monitor_id, "overlap", wait_for_body=True)
                body = data["response_body"]
                assert body["included"] and body["truncated"], body
                assert body["content"] == BODY[:limit], body
                assert data["request_body"]["included"] == (monitor_id != small), data
                if monitor_id == small:
                    assert data["request_body"]["content"] is None
                else:
                    assert json.loads(data["request_body"]["content"])["formData"] == {"secret": ["42"]}

            for monitor_id in (excluded, disabled):
                _, data = await content(monitor_id, "overlap")
                assert not data["response_body"]["included"], data
                assert data["response_body"]["content"] is None, data
                if monitor_id == disabled:
                    assert not data["request_body"]["included"], data
                    assert data["request_body"]["content"] is None, data

            outsider = await start({}, pattern=capture_site + "/never*")
            response = await request("requests.get_content", {
                "monitor_id": outsider, "request_id": request_id})
            assert response["data"]["code"] == "REQUEST_NOT_FOUND", response
            response = await request("requests.get_content", {
                "monitor_id": "unknown", "request_id": request_id})
            assert response["data"]["code"] == "MONITOR_NOT_FOUND", response

            # Stop capture but retain the exact per-monitor policy and stored prefix.
            for monitor_id in (small, large, excluded, disabled, all_text):
                await call("requests_stop_monitoring", monitor_id=monitor_id)
                monitors.remove(monitor_id)
            _, small_data = await content(small, "overlap")
            _, large_data = await content(large, "overlap")
            assert small_data["response_body"]["content"] == BODY[:4]
            assert large_data["response_body"]["content"] == BODY[:40]

            only_disabled = await start({"capture_request_bodies": False,
                                         "capture_response_bodies": False})
            await fetch_body("disabled")
            _, data = await content(only_disabled, "disabled")
            assert not data["request_body"]["included"], data
            assert not data["response_body"]["included"], data
        finally:
            for monitor_id in monitors:
                await call("requests_stop_monitoring", monitor_id=monitor_id)
            if tab_id is not None:
                await call("tabs_close", tab_id=tab_id)
