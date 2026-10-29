"""Forwarding semantics shared by automatic workers and manual HTTP servers."""

import asyncio
import json
import os
import signal
import sys

import httpx
import pytest
import websockets
from fastmcp import Client

import test_imports
from server.single_instance import probe, runtime_directory
from test_config import connect_as_extension
from test_single_instance import shared, answer_tabs, exchange_extension_versions
import test_stdio_transport as stdio_tests


@pytest.mark.asyncio
async def test_all_routes_work_through_a_local_tcp_forwarder(shared):
    start, port = shared
    client = await start()
    await client.initialize()
    connections = set()

    async def copy(reader, writer):
        try:
            while chunk := await reader.read(65536):
                writer.write(chunk)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def forward(reader, writer):
        task = asyncio.current_task()
        connections.add(task)
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(
                "localhost", port
            )
            await asyncio.gather(copy(reader, upstream_writer),
                                 copy(upstream_reader, writer))
        finally:
            writer.close()
            connections.discard(task)

    relay = await asyncio.start_server(forward, "127.0.0.1", 0)
    forwarded_port = relay.sockets[0].getsockname()[1]
    assert forwarded_port != port
    try:
        address = f"127.0.0.1:{forwarded_port}"
        async with httpx.AsyncClient(trust_env=False) as http:
            response = await http.get(f"http://{address}/discovery")
            assert response.status_code == 200
            assert response.json()["server"] == "FoxMCP"
            assert "access-control-allow-origin" not in response.headers
        async with connect_as_extension(f"ws://{address}/", proxy=None) as extension:
            await exchange_extension_versions(extension)
            async with websockets.connect(f"ws://{address}/proxy", proxy=None) as proxy:
                assert json.loads(await proxy.recv())["type"] == "hello"
                await proxy.send(json.dumps({
                    "id": "forwarded", "type": "request",
                    "action": "tabs.list", "data": {}, "profile_id": extension.profile_id,
                }))
                request = json.loads(await asyncio.wait_for(extension.recv(), 5))
                await answer_tabs(extension, request, 44)
                reply = json.loads(await asyncio.wait_for(proxy.recv(), 5))
                assert reply["id"] == "forwarded"
                assert reply["data"]["tabs"][0]["id"] == 44
                assert extension.close_code is None
    finally:
        relay.close()
        await relay.wait_closed()
        tasks = list(connections)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_colliding_ids_are_remapped_and_replies_can_arrive_out_of_order(shared):
    start, port = shared
    client = await start()
    await client.initialize()
    async with connect_as_extension(f"ws://localhost:{port}") as extension:
        await exchange_extension_versions(extension)
        async with (
            websockets.connect(f"ws://localhost:{port}/proxy") as first,
            websockets.connect(f"ws://localhost:{port}/proxy") as second,
        ):
            await first.recv()
            await second.recv()
            request = {
                "id": "same-id",
                "type": "request",
                "action": "tabs.list",
                "profile_id": extension.profile_id, "data": {},
            }
            await first.send(json.dumps(request))
            one = json.loads(await asyncio.wait_for(extension.recv(), 10))
            await second.send(json.dumps(request))
            two = json.loads(await asyncio.wait_for(extension.recv(), 10))
            assert len({one["id"], two["id"], "same-id"}) == 3
            await answer_tabs(extension, two, 22)
            await answer_tabs(extension, one, 11)
            first_reply, second_reply = await asyncio.gather(
                first.recv(), second.recv()
            )
            assert (
                json.loads(first_reply)["id"]
                == json.loads(second_reply)["id"]
                == "same-id"
            )
            assert json.loads(first_reply)["data"]["tabs"][0]["id"] == 11
            assert json.loads(second_reply)["data"]["tabs"][0]["id"] == 22
        assert "Browser extension connected" in await client.call_tool(
            "debug_websocket_status"
        )
        assert extension.close_code is None


@pytest.mark.asyncio
async def test_local_file_transfer_stays_in_the_stdio_process(shared, tmp_path):
    start, port = shared
    client = await start()
    await client.initialize()
    path = tmp_path / "upload.txt"
    path.write_bytes(b"local upload data")
    async with connect_as_extension(f"ws://localhost:{port}") as extension:
        await exchange_extension_versions(extension)
        call = asyncio.create_task(
            client.call_tool("content_load_file", {"tab_id": 1, "path": str(path)})
        )
        request = json.loads(await asyncio.wait_for(extension.recv(), 10))
        assert request["action"] == "content.load_file"
        data = request["data"]
        async with httpx.AsyncClient(trust_env=False) as http:
            assert (await http.get(data["url"])).content == b"local upload data"
            assert (await http.get(data["url"])).status_code == 404
        await extension.send(
            json.dumps(
                {
                    "id": request["id"],
                    "type": "response",
                    "action": request["action"],
                    "data": {"fileId": data["fileId"]},
                }
            )
        )
        result = await call
        assert '"name": "upload.txt"' in result and data["url"] not in result


@pytest.mark.asyncio
async def test_proxy_joins_manual_http_server_without_changing_its_lifetime(
    tmp_path, monkeypatch, free_tcp_port, free_tcp_port_factory
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    port = free_tcp_port
    http_port = free_tcp_port_factory()
    info = None
    with (tmp_path / "manual.log").open("wb") as log:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            stdio_tests.SERVER_SCRIPT,
            "--port",
            str(port),
            "--mcp-port",
            str(http_port),
            "--disable-tools",
            "tabs",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=log,
        )
        try:
            deadline = asyncio.get_running_loop().time() + 20
            while info is None:
                info = await probe("localhost", port)
                if asyncio.get_running_loop().time() >= deadline:
                    pytest.fail("Manual server did not start")
                await asyncio.sleep(0.1)
            assert info["lifetime"] == "manual"
            client = await stdio_tests.StdioClient(
                port,
                [
                    "--single-instance",
                    "--single-instance-idle-timeout",
                    "1",
                ],
            ).start()
            try:
                await client.initialize()
                assert "tabs_list" in await client.list_tool_names()
                async with Client(f"http://localhost:{http_port}/mcp") as http:
                    assert "tabs_list" not in {
                        tool.name for tool in await http.list_tools()
                    }
                async with connect_as_extension(f"ws://localhost:{port}") as extension:
                    await exchange_extension_versions(extension)
                    call = asyncio.create_task(client.call_tool("tabs_list"))
                    request = json.loads(await asyncio.wait_for(extension.recv(), 10))
                    await answer_tabs(extension, request, 33)
                    assert "ID 33" in await call
                    async with Client(f"http://localhost:{http_port}/mcp") as http:
                        call = asyncio.create_task(http.call_tool("list_windows", {"profile_id": extension.profile_id}))
                        request = json.loads(
                            await asyncio.wait_for(extension.recv(), 10)
                        )
                        assert request["action"] == "windows.list"
                        await extension.send(
                            json.dumps(
                                {
                                    "id": request["id"],
                                    "type": "response",
                                    "action": request["action"],
                                    "data": {
                                        "windows": [
                                            {
                                                "id": 1,
                                                "type": "normal",
                                                "focused": True,
                                                "state": "normal",
                                                "tabs": [],
                                            }
                                        ]
                                    },
                                }
                            )
                        )
                        result = await asyncio.wait_for(call, 5)
                        assert not result.is_error
                        assert "1" in "".join(item.text for item in result.content)
            finally:
                await client.close()
            await asyncio.sleep(1.5)
            assert (await probe("localhost", port))["pid"] == info["pid"]
            assert process.returncode is None
            assert not list(runtime_directory().glob("*"))
        finally:
            if info:
                os.kill(info["pid"], signal.SIGTERM)
            else:
                process.terminate()
            await asyncio.wait_for(process.wait(), 15)


@pytest.mark.asyncio
async def test_monitor_started_after_disconnect_is_still_stopped(shared):
    start, port = shared
    first, second = await asyncio.gather(start(), start())
    await asyncio.gather(first.initialize(), second.initialize())
    async with connect_as_extension(f"ws://localhost:{port}") as extension:
        await exchange_extension_versions(extension)
        await first._send(
            {
                "jsonrpc": "2.0",
                "id": 50,
                "method": "tools/call",
                "params": {
                    "name": "requests_start_monitoring",
                    "arguments": {"profile_id": extension.profile_id, "url_patterns": ["<all_urls>"]},
                },
            }
        )
        request = json.loads(await asyncio.wait_for(extension.recv(), 10))
        first.process.kill()
        await first.process.wait()
        await extension.send(
            json.dumps(
                {
                    "id": request["id"],
                    "type": "response",
                    "action": request["action"],
                    "data": {"monitor_id": "late-monitor"},
                }
            )
        )
        stop = json.loads(await asyncio.wait_for(extension.recv(), 12))
        assert stop["action"] == "requests.stop_monitoring"
        assert stop["data"]["monitor_id"] == "late-monitor"
        await extension.send(
            json.dumps(
                {
                    "id": stop["id"],
                    "type": "response",
                    "action": stop["action"],
                    "data": {},
                }
            )
        )
        assert "Browser extension connected" in await second.call_tool(
            "debug_websocket_status"
        )


@pytest.mark.asyncio
async def test_each_client_lists_its_own_predefined_scripts(
    shared, tmp_path, monkeypatch
):
    start, port = shared
    folders = [tmp_path / "scripts-first", tmp_path / "scripts-second"]
    for index, folder in enumerate(folders):
        folder.mkdir()
        script = folder / f"script-{index}.py"
        script.write_text(
            f"#!/usr/bin/env python3\n# Script for client {index}\n", encoding="utf-8"
        )
        script.chmod(0o755)
    monkeypatch.setenv("FOXMCP_EXT_SCRIPTS", str(folders[0]))
    first = await start()
    await first.initialize()
    owner = (await probe("localhost", port))["pid"]
    monkeypatch.setenv("FOXMCP_EXT_SCRIPTS", str(folders[1]))
    second = await start()
    await second.initialize()
    descriptions = []
    for client in (first, second):
        tools = (await client.request("tools/list"))["tools"]
        descriptions.append(
            next(
                tool["description"]
                for tool in tools
                if tool["name"] == "content_execute_predefined"
            )
        )
    assert "script-0.py" in descriptions[0] and "script-1.py" not in descriptions[0]
    assert "script-1.py" in descriptions[1] and "script-0.py" not in descriptions[1]
    assert (await probe("localhost", port))["pid"] == owner
