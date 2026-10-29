"""Profile registration and routing must never implicitly select another browser."""
import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
import uuid
from unittest.mock import AsyncMock

import pytest

from server.server import FoxMCPServer
from server.browser_proxy import PROTOCOL_VERSION
from server.profile_names import FirefoxProfileNames
from server.version import VERSION


class Peer:
    remote_address = ("127.0.0.1", 12345)

    def __init__(self, profile_id=None, hello=None):
        self.profile_id = profile_id or str(uuid.uuid4())
        self.close_code = None
        self.messages = asyncio.Queue()
        self.ready = asyncio.Event()
        self.request = SimpleNamespace(headers={"Origin": "moz-extension://" + str(uuid.uuid4())})
        self.recv = AsyncMock(return_value=json.dumps(hello if hello is not None else {
            "type": "hello", "data": {"profile_id": self.profile_id,
                                       "protocol_version": PROTOCOL_VERSION, "version": VERSION}}))
        self.send = AsyncMock(side_effect=self.sent)

    async def sent(self, raw):
        if json.loads(raw).get("type") == "ready":
            self.ready.set()

    def __aiter__(self):
        return self

    async def __anext__(self):
        message = await self.messages.get()
        if message is None:
            raise StopAsyncIteration
        return message

    async def close(self, code=1000, reason=""):
        self.close_code, self.reason = code, reason
        await self.messages.put(None)


@pytest.fixture
def server():
    instance = FoxMCPServer(start_mcp=False)
    instance.profile_names = FirefoxProfileNames([])
    return instance


@asynccontextmanager
async def connected(server, peer=None):
    peer = peer or Peer()
    task = asyncio.create_task(server.handle_extension_connection(peer))
    try:
        await asyncio.wait_for(peer.ready.wait(), 1)
        yield peer
    finally:
        await peer.close()
        await task


def command(profile_id, request_id="request"):
    return {"id": request_id, "type": "request", "action": "tabs.list",
            "profile_id": profile_id, "data": {}}


@pytest.mark.asyncio
async def test_two_profiles_do_not_replace_each_other(server):
    async with connected(server) as first, connected(server) as second:
        assert set(server.profiles) == {first.profile_id, second.profile_id}
        assert first.close_code is second.close_code is None
        status = await server.get_extension_status()
        assert first.profile_id in status and second.profile_id in status
    assert not server.profiles
    assert "No browser extension" in await server.get_extension_status()


@pytest.mark.asyncio
async def test_duplicate_id_does_not_replace_owner(server):
    async with connected(server) as first:
        duplicate = Peer(first.profile_id)
        await server.handle_extension_connection(duplicate)
        assert duplicate.close_code == 4009
        assert first.close_code is None
        assert server.profiles[first.profile_id].extension_connection is first


@pytest.mark.asyncio
@pytest.mark.parametrize("hello", [None, [], {}, {"type": "hello", "data": {"version": VERSION}},
    {"type": "hello", "data": {"profile_id": str(uuid.uuid4()), "protocol_version": 2}},
    {"type": "hello", "data": {"profile_id": "not-a-uuid", "protocol_version": PROTOCOL_VERSION}}])
async def test_invalid_or_legacy_handshake_is_rejected(server, hello):
    peer = Peer()
    peer.recv.return_value = json.dumps(hello)
    await server.handle_extension_connection(peer)
    assert peer.close_code == 1008
    assert not server.profiles


@pytest.mark.asyncio
async def test_no_implicit_profile_even_with_only_one_connection(server):
    async with connected(server) as peer:
        peer.send.reset_mock()
        result = await server.send_request_and_wait({"id": "request", "action": "tabs.list"})
        assert "profile_id is required" in result["error"]
        peer.send.assert_not_called()


@pytest.mark.asyncio
async def test_same_request_ids_are_isolated_and_disconnect_is_local(server):
    async with connected(server) as first, connected(server) as second:
        a = asyncio.create_task(server.send_request_and_wait(command(first.profile_id)))
        b = asyncio.create_task(server.send_request_and_wait(command(second.profile_id)))
        await asyncio.sleep(0)
        await first.close()
        assert "disconnected" in (await a)["error"]
        assert not b.done()
        await second.messages.put(json.dumps({"id": "request", "type": "response", "data": {"tabs": [2]}}))
        response = await b
        assert response["data"]["tabs"] == [2]
        assert response["profile_id"] == second.profile_id


@pytest.mark.asyncio
async def test_another_profile_cannot_complete_pending_request(server):
    async with connected(server) as first, connected(server) as second:
        task = asyncio.create_task(server.send_request_and_wait(command(first.profile_id)))
        await asyncio.sleep(0)
        response = json.dumps({"id": "request", "type": "response", "data": {"tabs": []}})
        await second.messages.put(response)
        await asyncio.sleep(0)
        assert not task.done()
        await first.messages.put(response)
        assert (await task)["profile_id"] == first.profile_id


@pytest.mark.asyncio
async def test_discovery_reports_failures_without_hiding_healthy_profiles(server):
    async with connected(server) as first, connected(server) as second:
        windows = [{"id": 1, "tabs": [{"id": 1, "title": "Chosen window", "url": "https://example.org/"}]}]
        healthy, unhealthy = server.profiles[first.profile_id], server.profiles[second.profile_id]
        healthy.send_request_and_wait = AsyncMock(return_value={"type": "response", "data": {"windows": windows}})
        unhealthy.send_request_and_wait = AsyncMock(return_value={"error": "Request timed out"})
        result = (await server.list_profiles())["profiles"]
        assert result[0]["windows"] == windows
        assert result[0]["name"] is None and result[0]["name_error"]
        assert result[1]["error"] == "Request timed out"
        assert healthy.send_request_and_wait.call_args.kwargs["timeout"] == 5.0


@pytest.mark.asyncio
async def test_monitors_are_scoped_to_connection_even_with_identical_ids(server):
    async with connected(server) as first, connected(server) as second:
        a, b = server.profiles[first.profile_id], server.profiles[second.profile_id]
        server.register_monitor(a.profile_id, "monitor", "owner-a", a.connection_id)
        server.register_monitor(b.profile_id, "monitor", "owner-b", b.connection_id)
        b.disconnected()
        assert a.monitor_owners == {"monitor": "owner-a"}
        assert not b.monitor_owners
        server.forget_monitor(a.profile_id, "monitor", b.connection_id)
        assert "monitor" in a.monitor_owners


@pytest.mark.asyncio
async def test_all_browser_tools_require_explicit_profile(server):
    for tool in await server.mcp_app.list_tools():
        if tool.name in ("profiles_list", "debug_websocket_status"):
            assert "profile_id" not in tool.parameters.get("required", [])
        else:
            assert "profile_id" in tool.parameters["required"], tool.name
    with pytest.raises(Exception, match="profile_id"):
        await server.mcp_app.call_tool("tabs_list", {})


@pytest.mark.asyncio
async def test_old_profile_id_is_invalid_after_browser_restart(server):
    async with connected(server) as old:
        old_id = old.profile_id
    async with connected(server) as new:
        result = await server.send_request_and_wait(command(old_id))
        assert "not connected" in result["error"]
        assert new.profile_id != old_id


@pytest.mark.asyncio
async def test_bad_window_payload_and_unreadable_names_preserve_discovery(server):
    def unavailable(_origins):
        raise PermissionError("metadata unavailable")

    server.profile_names.resolve = unavailable
    async with connected(server) as first, connected(server) as second:
        server.profiles[first.profile_id].send_request_and_wait = AsyncMock(
            return_value={"type": "response", "data": "malformed"})
        server.profiles[second.profile_id].send_request_and_wait = AsyncMock(
            return_value={"type": "response", "data": {"windows": [{"id": 1}]}})
        profiles = (await server.list_profiles(populate=False))["profiles"]
        assert "Invalid windows" in profiles[0]["error"]
        assert profiles[1]["windows"] == [{"id": 1}]
        assert all(p["name"] is None and "PermissionError" in p["name_error"] for p in profiles)


@pytest.mark.asyncio
async def test_stale_cleanup_cannot_clear_a_new_connection(server):
    from server.browser_profile import BrowserProfile

    async with connected(server) as old:
        replacement = BrowserProfile(server, Peer(old.profile_id), old.profile_id, old.request.headers["Origin"])
        replacement.register_monitor("new-monitor", "owner")
        server.profiles[old.profile_id] = replacement
    assert server.profiles[old.profile_id] is replacement
    assert replacement.monitor_owners == {"new-monitor": "owner"}


@pytest.mark.asyncio
async def test_cloned_origins_are_not_given_a_misleading_known_name(server):
    first, second = Peer(), Peer()
    second.request.headers["Origin"] = first.request.headers["Origin"]
    server.profile_names.resolve = lambda origins: {
        origin: {"name": "Only registered original", "name_error": None} for origin in origins}
    async with connected(server, first), connected(server, second):
        profiles = (await server.list_profiles(include_windows=False))["profiles"]
        assert len(profiles) == 2
        assert all(p["name"] is None and "ambiguous" in p["name_error"] for p in profiles)
