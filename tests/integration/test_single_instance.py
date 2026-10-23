"""Real stdio processes sharing one browser connection, without Firefox."""

import asyncio
import json
import os
import signal

import httpx
import pytest
import pytest_asyncio

import test_imports
from server.single_instance import runtime_directory
from test_config import connect_as_extension
import test_stdio_transport as stdio_tests


async def eventually(predicate, timeout=15):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError()
        await asyncio.sleep(0.1)


@pytest_asyncio.fixture
async def shared(tmp_path, monkeypatch, free_tcp_port):
    # Each test owns its discovery files, worker and browser port.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    websocket_port = free_tcp_port
    metadata_path = runtime_directory() / f"instance-{websocket_port}.json"
    clients = []

    async def start(*extra):
        client = await stdio_tests.StdioClient(websocket_port, [
            "--single-instance", "--single-instance-idle-timeout", "2", *extra,
        ]).start()
        clients.append(client)
        return client

    yield start, metadata_path, websocket_port

    for client in clients:
        if client.process.returncode is None:
            await client.close()
    try:
        await eventually(lambda: not metadata_path.exists())
    except TimeoutError:
        metadata = json.loads(metadata_path.read_text())
        try:
            os.kill(metadata["pid"], signal.SIGTERM)
        except OSError:
            pass
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
    start, metadata_path, port = shared
    first, second = await asyncio.gather(start(), start())
    await asyncio.gather(first.initialize(), second.initialize())
    metadata = json.loads(metadata_path.read_text())
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
        assert json.loads(metadata_path.read_text())["pid"] == metadata["pid"]


@pytest.mark.asyncio
async def test_idle_shutdown_and_automatic_restart(shared):
    start, metadata_path, _ = shared
    first = await start()
    await first.initialize()
    old_pid = json.loads(metadata_path.read_text())["pid"]
    assert await first.close() == 0
    await eventually(lambda: not metadata_path.exists())

    second = await start()
    await second.initialize()
    assert json.loads(metadata_path.read_text())["pid"] != old_pid
    assert "tabs_list" in await second.list_tool_names()


@pytest.mark.asyncio
async def test_crashed_owner_leaves_no_lock_and_stale_metadata_is_replaced(shared):
    start, metadata_path, _ = shared
    first = await start()
    await first.initialize()
    old_pid = json.loads(metadata_path.read_text())["pid"]
    os.kill(old_pid, signal.SIGTERM)
    # Existing sessions need reconnecting after a crash; no in-flight operation
    # is retried, since it may already have changed the browser.
    await first.close()

    second = await start()
    await second.initialize()
    assert json.loads(metadata_path.read_text())["pid"] != old_pid
    assert "tabs_list" in await second.list_tool_names()


@pytest.mark.asyncio
async def test_tool_configuration_is_preserved_and_mismatch_is_refused(shared):
    start, _, _ = shared
    first = await start("--disable-tools", "history,bookmarks")
    await first.initialize()
    names = await first.list_tool_names()
    assert "tabs_list" in names
    assert not any(name.startswith(("history_", "bookmarks_")) for name in names)

    second = await start()
    await asyncio.wait_for(second.process.wait(), 15)
    assert second.process.returncode != 0
    assert await second.process.stdout.read() == b""
    assert "different code or tool/script settings" in await second._read_stderr()
    assert "tabs_list" in await first.list_tool_names()


@pytest.mark.asyncio
async def test_private_endpoint_requires_token_and_rejects_page_origins(shared):
    start, metadata_path, _ = shared
    client = await start()
    await client.initialize()
    metadata = json.loads(metadata_path.read_text())
    url = f"http://127.0.0.1:{metadata['port']}/mcp"
    async with httpx.AsyncClient() as http:
        assert (await http.get(url)).status_code == 403
        assert (await http.get(url, headers={
            "Authorization": f"Bearer {metadata['token']}",
            "Origin": "https://example.org",
        })).status_code == 403
        assert (await http.post(url, content="{}", headers={
            "Content-Type": "text/plain",
        })).status_code == 403


@pytest.mark.asyncio
async def test_monitors_are_cleaned_up_per_chat(shared):
    start, _, port = shared
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
