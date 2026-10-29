"""Two profiles and independent HTTP/stdio clients sharing one browser port."""

import asyncio
from contextlib import AsyncExitStack
import json
from pathlib import Path
import sys

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from server.server import FoxMCPServer
from server.profile_names import FirefoxProfileNames
from test_config import connect_as_extension
from firefox_test_utils import FirefoxTestManager, resolve_firefox_path


async def until(predicate, timeout=20):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Timed out waiting for profile state")
        await asyncio.sleep(0.05)


class SimulatedProfile:
    """Identical native IDs in distinct profiles deliberately collide."""
    def __init__(self, socket, label):
        self.socket, self.label = socket, label
        self.received = []
        self.monitors = set()
        self.holding = asyncio.Event()

    async def answer(self):
        async for raw in self.socket:
            request = json.loads(raw)
            if request.get("type") != "request":
                continue
            self.received.append(request)
            action, data = request["action"], request["data"]
            tab = {"id": 1, "windowId": 1, "index": 0, "active": True,
                   "title": self.label, "url": "https://example.org/" + self.label}
            if action == "windows.list":
                result = {"windows": [{"id": 1, "focused": True, "state": "normal", "tabs": [tab]}]}
            elif action == "tabs.list":
                result = {"tabs": [tab]}
            elif action == "content.execute_script":
                if data["script"] == "hold":
                    self.holding.set()
                    await asyncio.Event().wait()
                result = {"result": self.label}
            elif action == "requests.start_monitoring":
                self.monitors.add("same-monitor-id")
                result = {"monitor_id": "same-monitor-id"}
            elif action == "requests.stop_monitoring":
                self.monitors.discard(data["monitor_id"])
                result = {"monitor_id": data["monitor_id"], "status": "stopped"}
            elif action == "content.load_file":
                async with httpx.AsyncClient(trust_env=False) as client:
                    assert (await client.get(data["url"])).content == b"selected profile upload"
                result = {"fileId": data["fileId"]}
            else:
                raise AssertionError(action)
            await self.socket.send(json.dumps({"id": request["id"], "type": "response",
                                               "action": action, "data": result}))


@pytest.mark.asyncio
async def test_profiles_are_visible_and_routable_from_http_and_shared_stdio(free_tcp_port, free_tcp_port_factory, tmp_path):
    server = FoxMCPServer(port=free_tcp_port, mcp_port=free_tcp_port_factory())
    server.profile_names = FirefoxProfileNames([])
    server.MONITOR_REAP_INTERVAL = 0.1
    task = asyncio.create_task(server.start_server())
    responders = []
    try:
        await until(lambda: server.mcp_server_instance and server.mcp_server_instance.started)
        async with AsyncExitStack() as stack:
            a = await stack.enter_async_context(connect_as_extension(f"ws://localhost:{server.port}"))
            b = await stack.enter_async_context(connect_as_extension(f"ws://localhost:{server.port}"))
            peers = [SimulatedProfile(a, "alpha"), SimulatedProfile(b, "beta")]
            responders = [asyncio.create_task(p.answer()) for p in peers]
            http = await stack.enter_async_context(Client(f"http://localhost:{server.mcp_port}/mcp"))
            stdio = await stack.enter_async_context(Client(StdioTransport(
                sys.executable, [str(Path(__file__).resolve().parents[2] / "server/server.py"),
                                 "--stdio", "--single-instance", "--port", str(server.port)])))
            snapshots = await asyncio.gather(*(c.call_tool("profiles_list", {}) for c in (http, stdio)))
            for snapshot in snapshots:
                profiles = json.loads(snapshot.content[0].text)["profiles"]
                assert {p["profile_id"] for p in profiles} == {a.profile_id, b.profile_id}
                assert {p["windows"][0]["tabs"][0]["title"] for p in profiles} == {"alpha", "beta"}
                assert all(p["name"] is None and p["name_error"] for p in profiles)
            results = await asyncio.gather(
                http.call_tool("content_execute_script", {"profile_id": b.profile_id, "tab_id": 1, "code": "label"}),
                stdio.call_tool("content_execute_script", {"profile_id": a.profile_id, "tab_id": 1, "code": "label"}))
            assert "beta" in results[0].content[0].text
            assert "alpha" in results[1].content[0].text
            source = tmp_path / "upload.txt"
            source.write_bytes(b"selected profile upload")
            result = await stdio.call_tool("content_load_file", {
                "profile_id": b.profile_id, "tab_id": 1, "path": str(source)})
            assert not result.is_error and '"file_id"' in result.content[0].text
            assert not any(r["action"] == "content.load_file" for r in peers[0].received)
            for profile in (a, b):
                await http.call_tool("requests_start_monitoring", {
                    "profile_id": profile.profile_id, "url_patterns": ["https://example.org/*"]})
            assert all(p.monitors == {"same-monitor-id"} for p in peers)
            pending = asyncio.create_task(http.call_tool("content_execute_script", {
                "profile_id": a.profile_id, "tab_id": 1, "code": "hold"}))
            await asyncio.wait_for(peers[0].holding.wait(), 5)
            await a.close()
            assert "disconnected" in (await asyncio.wait_for(pending, 5)).content[0].text
            assert b.profile_id in server.profiles
            assert server.profiles[b.profile_id].monitor_owners
            assert "beta" in (await stdio.call_tool("tabs_list", {"profile_id": b.profile_id})).content[0].text
            await http.close()
            await until(lambda: not peers[1].monitors)
    finally:
        for responder in responders:
            responder.cancel()
        await asyncio.gather(*responders, return_exceptions=True)
        await server.shutdown(task)


@pytest.mark.asyncio
async def test_two_real_firefox_profiles_reconnect_and_restart_independently(free_tcp_port, tmp_path):
    firefox_path = resolve_firefox_path()
    assert firefox_path, "Firefox is required for the multi-profile acceptance test"
    server = FoxMCPServer(port=free_tcp_port, start_mcp=False)
    server.profile_names = FirefoxProfileNames([tmp_path])
    managers = [FirefoxTestManager(firefox_path=firefox_path, test_port=server.port,
                                   cache_profiles=False) for _ in range(2)]
    await server.start_browser_listener()
    try:
        for manager in managers:
            assert await asyncio.to_thread(manager.setup_and_start_firefox, headless=True, skip_on_failure=False)
        await until(lambda: len(server.profiles) == 2)
        (tmp_path / "profiles.ini").write_text("\n".join(
            f"[Profile{i}]\nName={name}\nIsRelative=0\nPath={manager.profile_dir}\n"
            for i, (name, manager) in enumerate(zip(("Alpha", "Beta"), managers))), encoding="utf-8")
        profiles = (await server.list_profiles())["profiles"]
        by_name = {p["name"]: p for p in profiles}
        assert set(by_name) == {"Alpha", "Beta"}, profiles
        alpha, beta = by_name["Alpha"]["profile_id"], by_name["Beta"]["profile_id"]
        tool = (await server.mcp_app.get_tool("tabs_create")).fn
        for profile_id, label in ((alpha, "alpha"), (beta, "beta")):
            result = await tool(profile_id=profile_id, url="https://example.org/#" + label)
            assert "Created" in result or "created" in result
        for profile_id, label, other in ((alpha, "alpha", "beta"), (beta, "beta", "alpha")):
            listing = await (await server.mcp_app.get_tool("tabs_list")).fn(profile_id=profile_id)
            assert "#" + label in listing and "#" + other not in listing
        old_connection = server.profiles[alpha]
        await old_connection.extension_connection.close()
        await until(lambda: alpha not in server.profiles and len(server.profiles) == 2)
        reconnected_alpha = next(key for key in server.profiles if key != beta)
        assert reconnected_alpha > max(alpha, beta)
        stale = await server.send_request_and_wait({"id": "reconnect-stale", "type": "request",
            "action": "tabs.list", "profile_id": alpha, "data": {}})
        assert "not connected" in stale["error"]
        assert beta in server.profiles
        assert await asyncio.to_thread(managers[0].restart_firefox)
        await until(lambda: reconnected_alpha not in server.profiles and len(server.profiles) == 2)
        assert beta in server.profiles
        result = await server.send_request_and_wait({"id": "stale", "type": "request",
            "action": "tabs.list", "profile_id": alpha, "data": {}})
        assert "not connected" in result["error"]
        assert (await server.list_profiles())["profiles"]
    finally:
        for manager in managers:
            await asyncio.to_thread(manager.cleanup)
        await server._stop()
