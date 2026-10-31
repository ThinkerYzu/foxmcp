"""Install current release archives and launch them through each PowerShell host."""

import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import subprocess
import threading

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
import pytest


ROOT = Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@pytest.mark.asyncio
async def test_clean_install_http_and_stdio(tmp_path):
    shell = os.environ.get("FOXMCP_TEST_POWERSHELL", "powershell")
    install = tmp_path / "installation with spaces"
    install.mkdir()
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    downloads = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=downloads.serve_forever, daemon=True)
    thread.start()
    env = os.environ.copy()
    origin = f"http://127.0.0.1:{downloads.server_port}"
    env["FOXMCP_RELEASE_URL"] = origin + "/dist/packages"
    env["FOXMCP_SOURCE_URL"] = origin
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(ROOT / "scripts/install-from-github.ps1"), "-NonInteractive"],
            cwd=install, env=env, capture_output=True, text=True, timeout=300)
        (tmp_path / "install.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        downloads.shutdown()
        downloads.server_close()
        thread.join(timeout=5)
    assert (install / "server/server.py").is_file()
    assert not (install / "server/server-package").exists()
    assert (install / "venv/Scripts/python.exe").is_file()
    assert (install / "predefined-scripts/set-file-input.py").is_file()
    launcher = [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(install / "start-foxmcp.ps1")]
    ws, http = free_port(), free_port()
    with (tmp_path / "http.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(launcher + ["--port", str(ws), "--mcp-port", str(http)],
                                  cwd=tmp_path, stdout=log, stderr=log)
        try:
            deadline = asyncio.get_running_loop().time() + 40
            while True:
                assert server.poll() is None, (tmp_path / "http.log").read_text()
                try:
                    async with Client(f"http://localhost:{http}/mcp/", timeout=5) as client:
                        names = {tool.name for tool in await client.list_tools()}
                        assert len(names) == 46
                        assert {"profiles_list", "content_execute_predefined"} <= names
                    break
                except (RuntimeError, OSError):
                    if asyncio.get_running_loop().time() >= deadline:
                        raise
                    await asyncio.sleep(.25)
        finally:
            subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"],
                           capture_output=True, timeout=15)
            server.wait(timeout=15)
    # Stdio clients launch Python directly, preserving the protocol streams.
    direct = StdioTransport(command=str(install / "venv/Scripts/python.exe"),
                            args=[str(install / "server/server.py"), "--stdio",
                                  "--port", str(free_port())], cwd=str(tmp_path))
    async with Client(direct, timeout=30) as client:
        assert len(await client.list_tools()) == 46
        result = await client.call_tool("tabs_list", {"profile_id": 1})
        assert "profile is not connected" in result.content[0].text
    # The HTTP helper refuses an unsupported protocol relay immediately and
    # points clients at the direct Python command verified above.
    refused = await asyncio.to_thread(
        subprocess.run, launcher + ["--stdio"], cwd=tmp_path,
        capture_output=True, text=True, timeout=15)
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert "launch Python directly" in refused.stderr
    assert str(install / "venv/Scripts/python.exe") in refused.stderr
    # Exercise the helper only on a disposable directory, never a real profile.
    profile = tmp_path / "disposable Firefox profile"
    profile.mkdir()
    (profile / "prefs.js").write_text("// fixture\n")
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
         str(install / "scripts/install-xpi.ps1"), str(profile)],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (profile / "extensions/foxmcp@codemud.org.xpi").read_bytes() == (
        install / "dist/packages/foxmcp@codemud.org.xpi").read_bytes()
