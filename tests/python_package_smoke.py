#!/usr/bin/env python3
"""Check an installed wheel/sdist from an empty directory, without the checkout.

Run with the installation's Python. CI copies this file outside the checkout
before running it so neither imports nor resources can come from source.
"""

import asyncio
from contextlib import suppress
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import uuid

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
import websockets

EXAMPLES = {
    "dom-summarize.sh",
    "gcal-cal-event-js.sh",
    "gcal-daily-events-js.sh",
    "gcal-monthly-events-js.sh",
    "set-file-input.py",
    "youtube-play-pause.sh",
}


def unused_port() -> int:
    """Ask the OS for a temporary loopback port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def answer_extension(port: int, ready: asyncio.Event, scripts: list, profile_id: str) -> None:
    """Stand in for Firefox to verify the installed command's bridge."""
    for attempt in range(200):
        try:
            connection = await websockets.connect(
                f"ws://127.0.0.1:{port}", origin="moz-extension://package-smoke"
            )
            break
        except OSError:
            if attempt == 199:
                raise
            await asyncio.sleep(0.1)
    try:
        await connection.send(json.dumps({
            "type": "hello", "data": {"version": distribution("foxmcp").version, "protocol_version": 3, "profile_id": profile_id}
        }))
        async for raw in connection:
            request = json.loads(raw)
            if request.get("type") == "hello":
                assert request["data"]["version"] == distribution("foxmcp").version, request
                continue
            if request.get("type") == "ready":
                ready.set()
                continue
            action = request.get("action")
            if action == "windows.list":
                data = {"windows": [{"id": 1, "tabs": []}]}
            elif action == "tabs.list":
                data = {
                    "tabs": [
                        {
                            "id": 1,
                            "windowId": 1,
                            "index": 0,
                            "title": "Package smoke",
                            "url": "https://example.org/",
                            "active": True,
                        }
                    ]
                }
            elif action == "content.execute_script":
                scripts.append(request["data"]["script"])
                data = {"result": "packaged-script-ok"}
            else:
                raise AssertionError(f"Unexpected extension action: {action}")
            await connection.send(
                json.dumps(
                    {
                        "id": request["id"],
                        "type": "response",
                        "action": action,
                        "data": data,
                    }
                )
            )

    finally:
        await connection.close()


async def check_client(client: Client, port: int, script_name: str | None) -> None:
    """Verify discovery, a bridge call, and execution of a packaged/custom script."""
    ready = asyncio.Event()
    scripts = []
    profile_id = str(uuid.uuid4())
    extension = asyncio.create_task(answer_extension(port, ready, scripts, profile_id))
    try:
        await asyncio.wait_for(ready.wait(), 25)
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert len(tools) == 46, sorted(tools)
        description = tools["content_execute_predefined"].description
        if script_name == "dom-summarize.sh":
            assert all(name in description for name in EXAMPLES), description
        elif script_name:
            assert script_name in description, description
            assert "dom-summarize.sh" not in description, description
        else:
            assert "FOXMCP_EXT_SCRIPTS is not set" in description, description
        profiles = await client.call_tool("profiles_list", {})
        assert profile_id in profiles.content[0].text, profiles
        result = await client.call_tool("tabs_list", {"profile_id": profile_id})
        assert "Package smoke" in result.content[0].text, result
        result = await client.call_tool(
            "content_execute_predefined",
            {
                "profile_id": profile_id,
                "tab_id": 1,
                "script_name": script_name or "dom-summarize.sh",
            },
        )
        if script_name:
            assert "packaged-script-ok" in result.content[0].text, result
            assert len(scripts) == 1
            expected = "document" if script_name == "dom-summarize.sh" else "custom-package-example"
            assert expected in scripts[0], scripts[0]
        else:
            assert "environment variable not set" in result.content[0].text, result
            assert not scripts
    finally:
        extension.cancel()
        with suppress(asyncio.CancelledError):
            await extension


async def check_stdio(command: str, env: dict, script_name: str | None) -> None:
    """Start the real console command through an MCP stdio transport."""
    port = unused_port()
    transport = StdioTransport(command, ["--stdio", "--port", str(port)], env=env)
    async with Client(transport) as client:
        await check_client(client, port, script_name)


async def check_http(command: str, env: dict) -> None:
    """Start the console command in its default HTTP mode."""
    port, mcp_port = unused_port(), unused_port()
    while mcp_port == port:
        mcp_port = unused_port()
    with open("http-server.log", "w") as log:
        process = subprocess.Popen(
            [command, "--port", str(port), "--mcp-port", str(mcp_port)],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for attempt in range(200):
                assert process.poll() is None, Path("http-server.log").read_text()
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", mcp_port)
                except OSError:
                    await asyncio.sleep(0.1)
                else:
                    writer.close()
                    await writer.wait_closed()
                    break
            else:
                raise AssertionError("HTTP listener never started")
            async with Client(f"http://127.0.0.1:{mcp_port}/mcp/") as client:
                await check_client(client, port, "dom-summarize.sh")
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)


async def smoke(command: str, env: dict) -> None:
    """Exercise both transports and script-directory override semantics."""
    await check_http(command, env)
    await check_stdio(command, env, "dom-summarize.sh")
    custom = Path("custom-scripts").resolve()
    custom.mkdir()
    script = custom / "custom.sh"
    script.write_text("#!/bin/sh\n# Custom package example.\necho \"'custom-package-example'\"\n")
    script.chmod(0o755)
    await check_stdio(command, dict(env, FOXMCP_EXT_SCRIPTS=str(custom)), "custom.sh")
    await check_stdio(command, dict(env, FOXMCP_EXT_SCRIPTS=""), None)


def main() -> None:
    """Validate installed metadata, resources, CLI failures and MCP behavior."""
    import foxmcp
    from foxmcp.server import HAS_PORT_COORDINATOR

    package = Path(foxmcp.__file__).parent
    assert sys.prefix != sys.base_prefix, "Run in a clean installation venv"
    assert package.is_relative_to(Path(sys.prefix)), package
    assert not HAS_PORT_COORDINATOR, "Tests leaked from source into the installation"
    metadata = distribution("foxmcp")
    assert metadata.version == sys.argv[1], metadata.version
    assert metadata.metadata["Requires-Python"] == ">=3.10"
    examples = package / "examples"
    assert {p.name for p in examples.iterdir() if p.suffix in (".sh", ".py")} == EXAMPLES
    assert all(os.access(examples / name, os.X_OK) for name in EXAMPLES)
    command = str(Path(sys.executable).with_name("foxmcp"))
    env = os.environ.copy()
    for name in ("PYTHONPATH", "FOXMCP_EXT_SCRIPTS", "FOXMCP_DISABLE_TOOLS", "FOXMCP_ENABLE_TOOLS"):
        env.pop(name, None)
    help_result = subprocess.run(
        [command, "--help"], env=env, capture_output=True, text=True, timeout=30
    )
    assert help_result.returncode == 0 and "--stdio" in help_result.stdout, help_result
    invalid = subprocess.run(
        [command, "--stdio", "--mcp-port", "3000"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert invalid.returncode == 2, invalid
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        failed = subprocess.run(
            [command, "--stdio", "--port", str(busy.getsockname()[1])],
            env=env,
            input="",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert failed.returncode == 1 and "Cannot listen" in failed.stderr, failed
    with tempfile.TemporaryDirectory(prefix="foxmcp-python-smoke-") as directory:
        os.chdir(directory)
        asyncio.run(asyncio.wait_for(smoke(command, env), timeout=180))
    print(
        f"Installed foxmcp {metadata.version}: HTTP, stdio, scripts, overrides and CLI errors passed"
    )


if __name__ == "__main__":
    main()
