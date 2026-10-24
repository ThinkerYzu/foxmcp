"""Real stdio processes sharing one browser connection, without Firefox."""

import asyncio
import json
import os
import signal
import sys

import httpx
import websockets
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import test_imports
from server.single_instance import probe, runtime_directory
from test_config import connect_as_extension
import test_stdio_transport as stdio_tests


async def wait_until_stopped(port):
    deadline = asyncio.get_running_loop().time() + 15
    while await probe("localhost", port) is not None:
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError("Shared server did not stop")
        await asyncio.sleep(0.1)


@pytest_asyncio.fixture
async def shared(tmp_path, monkeypatch, free_tcp_port):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    clients = []

    async def start(*extra):
        client = await stdio_tests.StdioClient(free_tcp_port, [
            "--single-instance", "--single-instance-idle-timeout", "2", *extra,
        ]).start()
        clients.append(client)
        return client

    yield start, free_tcp_port

    for client in clients:
        if client.process.returncode is None:
            await client.close()
    try:
        await wait_until_stopped(free_tcp_port)
    except TimeoutError:
        info = await probe("localhost", free_tcp_port)
        if info:
            os.kill(info["pid"], signal.SIGTERM)
        pytest.fail("Shared server did not stop after its last client left")


async def answer_tabs(extension, request, tab_id):
    await extension.send(json.dumps({
        "id": request["id"], "type": "response", "action": "tabs.list",
        "data": {"tabs": [{"id": tab_id, "url": "https://example.org/",
                           "title": f"Tab {tab_id}", "active": True,
                           "windowId": 1, "index": 0}]},
    }))


@pytest.mark.asyncio
async def test_simultaneous_clients_share_browser_and_route_replies(shared):
    start, port = shared
    first, second = await asyncio.gather(start(), start())
    await asyncio.gather(first.initialize(), second.initialize())
    metadata = (await probe("localhost", port))
    assert metadata["pid"] not in (first.process.pid, second.process.pid)

    async with connect_as_extension(f"ws://localhost:{port}") as extension:
        calls = [asyncio.create_task(client.call_tool("tabs_list"))
                 for client in (first, second)]
        requests = [json.loads(await asyncio.wait_for(extension.recv(), 10)) for _ in calls]
        assert requests[0]["id"] != requests[1]["id"]
        # Responses arriving in reverse order must still reach the right chat.
        for request in reversed(requests):
            await answer_tabs(extension, request, 7)
        answers = await asyncio.gather(*calls)
        assert all("ID 7" in answer for answer in answers)
        assert all(json.loads(line)["jsonrpc"] == "2.0"
                   for client in (first, second) for line in client.stdout_lines)

        # The first chat can be killed by its owner without taking Firefox away.
        first.process.kill()
        await first.process.wait()
        call = asyncio.create_task(second.call_tool("tabs_list"))
        request = json.loads(await asyncio.wait_for(extension.recv(), 10))
        await answer_tabs(extension, request, 8)
        assert "ID 8" in await call
        assert not extension.close_code
        assert (await probe("localhost", port))["pid"] == metadata["pid"]


@pytest.mark.asyncio
async def test_sdk_client_cleanup_does_not_kill_shared_worker(shared):
    """Windows SDK clients kill their Job Object, including detached children."""
    _, port = shared

    def client():
        return Client(StdioTransport(
            command=sys.executable,
            args=[stdio_tests.SERVER_SCRIPT, "--stdio", "--single-instance",
                  "--single-instance-idle-timeout", "2", "--port", str(port)],
            env={name: os.environ[name] for name in ("LOCALAPPDATA", "XDG_RUNTIME_DIR")},
        ), init_timeout=30)

    first, second = client(), client()
    async with first:
        owner = (await probe("localhost", port))["pid"]
        async with second:
            await first.close()
            assert "tabs_list" in {tool.name for tool in await second.list_tools()}
            assert (await probe("localhost", port))["pid"] == owner


@pytest.mark.asyncio
async def test_idle_shutdown_and_automatic_restart(shared):
    start, port = shared
    first = await start()
    await first.initialize()
    old_pid = (await probe("localhost", port))["pid"]
    assert await first.close() == 0
    await wait_until_stopped(port)

    second = await start()
    await second.initialize()
    assert (await probe("localhost", port))["pid"] != old_pid
    assert "tabs_list" in await second.list_tool_names()


@pytest.mark.asyncio
async def test_crashed_owner_is_replaced_on_next_launch(shared):
    start, port = shared
    first = await start()
    await first.initialize()
    old_pid = (await probe("localhost", port))["pid"]
    os.kill(old_pid, signal.SIGTERM)
    # Existing sessions need reconnecting after a crash; no in-flight operation
    # is retried, since it may already have changed the browser.
    await first.close()

    second = await start()
    await second.initialize()
    assert (await probe("localhost", port))["pid"] != old_pid
    assert "tabs_list" in await second.list_tool_names()


@pytest.mark.asyncio
async def test_each_client_keeps_its_own_tool_configuration(shared):
    start, port = shared
    first = await start("--disable-tools", "history,bookmarks")
    await first.initialize()
    owner = (await probe("localhost", port))["pid"]
    second = await start()
    await second.initialize()
    names = await first.list_tool_names()
    assert "tabs_list" in names
    assert not any(name.startswith(("history_", "bookmarks_")) for name in names)
    assert "history_query" in await second.list_tool_names()
    assert (await probe("localhost", port))["pid"] == owner
    assert not list(runtime_directory().glob("*.json"))
    assert not list(runtime_directory().glob("*.lock"))


@pytest.mark.asyncio
async def test_discovery_and_proxy_reject_page_origins_and_spoofed_hosts(shared):
    start, port = shared
    client = await start()
    await client.initialize()
    async with connect_as_extension(f"ws://localhost:{port}") as extension:
        async with httpx.AsyncClient(trust_env=False) as http:
            for headers in ({"Origin": "https://example.org"}, {"Origin": "null"},
                            {"Host": "example.org"}):
                response = await http.get(f"http://localhost:{port}/discovery", headers=headers)
                assert response.status_code == 403
                assert "access-control-allow-origin" not in response.headers
        for origin in ("https://example.org", "null", "moz-extension://other"):
            with pytest.raises(websockets.exceptions.InvalidStatus) as rejection:
                await websockets.connect(f"ws://localhost:{port}/proxy", origin=origin)
            assert rejection.value.response.status_code == 403
        assert extension.close_code is None


@pytest.mark.asyncio
async def test_monitors_are_cleaned_up_per_chat(shared):
    start, port = shared
    first, second = await asyncio.gather(start(), start())
    await asyncio.gather(first.initialize(), second.initialize())
    async with connect_as_extension(f"ws://localhost:{port}") as extension:
        for client, monitor_id in ((first, "monitor-first"), (second, "monitor-second")):
            call = asyncio.create_task(client.call_tool("requests_start_monitoring",
                                                        {"url_patterns": ["<all_urls>"]}))
            request = json.loads(await asyncio.wait_for(extension.recv(), 10))
            assert request["action"] == "requests.start_monitoring"
            await extension.send(json.dumps({
                "id": request["id"], "type": "response", "action": request["action"],
                "data": {"monitor_id": monitor_id},
            }))
            assert monitor_id in await call
        first.process.kill()
        await first.process.wait()
        stop = json.loads(await asyncio.wait_for(extension.recv(), 12))
        assert stop["action"] == "requests.stop_monitoring"
        assert stop["data"]["monitor_id"] == "monitor-first"
        await extension.send(json.dumps({
            "id": stop["id"], "type": "response", "action": stop["action"],
            "data": {"monitor_id": "monitor-first"},
        }))
        assert "tabs_list" in await second.list_tool_names()


@pytest.mark.asyncio
async def test_single_instance_requires_stdio():
    runner = stdio_tests.TestOptionsThatCannotBeCombined()
    code, stdout, stderr = await runner.run_with("--single-instance")
    assert code != 0 and not stdout
    assert "--single-instance requires --stdio" in stderr
