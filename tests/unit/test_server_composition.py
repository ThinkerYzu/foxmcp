"""Startup roles must construct only the components shown in the architecture."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server import server, single_instance
from server.browser_profile import BrowserProfile
from server.browser_server import BrowserServer
from server.mcp_frontend import MCPFrontend
from server.mcp_tools import FoxMCPTools


def forbidden(*args, **kwargs):
    raise AssertionError("This startup role must not construct this component")


@pytest.mark.asyncio
async def test_worker_never_constructs_mcp_tools(monkeypatch):
    monkeypatch.setattr(FoxMCPTools, "__init__", forbidden)
    monkeypatch.setattr(server, "MCPFrontend", forbidden)
    captured = []

    async def worker(browser, timeout):
        assert isinstance(browser, BrowserServer)
        assert not hasattr(browser, "frontend")
        assert not hasattr(browser, "file_transfers")
        assert browser.proxy_hub.browser_server is browser
        captured.append(timeout)

    monkeypatch.setattr(single_instance, "run_worker", worker)
    monkeypatch.setattr(server.sys, "argv", ["server.py", "--stdio", "--single-instance",
                                             "--single-instance-worker"])
    await server.main()
    assert captured == [60.0]


@pytest.mark.asyncio
async def test_browser_only_startup_never_constructs_frontend(monkeypatch):
    monkeypatch.setattr(FoxMCPTools, "__init__", forbidden)
    monkeypatch.setattr(server, "MCPFrontend", forbidden)
    serve = AsyncMock()
    monkeypatch.setattr(server, "serve", serve)
    monkeypatch.setattr(server.sys, "argv", ["server.py", "--no-mcp"])
    await server.main()
    browser, frontend = serve.call_args.args
    assert isinstance(browser, BrowserServer)
    assert frontend is None


@pytest.mark.asyncio
async def test_shared_frontend_never_constructs_browser_owner(monkeypatch):
    monkeypatch.setattr(server, "BrowserServer", forbidden)
    websocket = AsyncMock()
    websocket.__aiter__.return_value = []
    discover = AsyncMock(return_value=websocket)
    monkeypatch.setattr(single_instance, "discover", discover)
    captured = []

    async def serve_stdio(frontend):
        assert isinstance(frontend.browser, single_instance.RemoteBrowser)
        assert frontend.tools.browser is frontend.browser
        assert frontend.tools.file_transfers is frontend.file_transfers
        assert not hasattr(frontend.browser, "profiles")
        assert not hasattr(frontend.browser, "file_transfers")
        names = {tool.name for tool in await frontend.app.list_tools()}
        assert "tabs_list" in names and "tabs_create" not in names
        captured.append(frontend)

    monkeypatch.setattr(MCPFrontend, "serve_stdio", serve_stdio)
    monkeypatch.setattr(server.sys, "argv", ["server.py", "--stdio", "--single-instance",
        "--disable-tools", "tabs", "--enable-tools", "tabs_list"])
    await server.main()
    assert len(captured) == 1
    assert discover.call_args.args[0] == single_instance.BrowserEndpoint("localhost", 8765)
    websocket.close.assert_awaited_once()
    assert captured[0].browser.reader.done()


@pytest.mark.asyncio
async def test_local_frontend_uses_browser_directly_and_owns_file_service(tmp_path):
    browser = BrowserServer()
    frontend = MCPFrontend(browser, use_stdio=True)
    try:
        assert frontend.browser is frontend.tools.browser is browser
        assert not hasattr(browser, "file_transfers")
        path = tmp_path / "local.txt"
        path.write_text("local upload")
        frontend.file_transfers.grant(path)
    finally:
        await frontend.close()
    assert not frontend.file_transfers._thread.is_alive()


@pytest.mark.asyncio
async def test_http_monitor_liveness_is_supplied_by_frontend():
    browser = BrowserServer()
    frontend = MCPFrontend(browser, use_stdio=True)
    profile = BrowserProfile(browser, object(), 1, "moz-extension://test")
    browser.profiles[1] = profile
    profile.send_request_and_wait = AsyncMock(return_value={"type": "response", "data": {}})
    session = SimpleNamespace(is_terminated=False)
    manager = SimpleNamespace(_server_instances={"client": session})
    frontend.http_app = SimpleNamespace(routes=[SimpleNamespace(
        app=SimpleNamespace(session_manager=manager))])
    browser.live_mcp_session_ids = frontend.live_mcp_session_ids
    profile.register_monitor("monitor", "client")
    try:
        await browser.stop_monitors_of_gone_clients()
        profile.send_request_and_wait.assert_not_awaited()
        session.is_terminated = True
        await browser.stop_monitors_of_gone_clients()
        assert profile.send_request_and_wait.call_args.args[0]["action"] == "requests.stop_monitoring"
        assert not profile.monitor_owners
    finally:
        await frontend.close()


@pytest.mark.parametrize("name", ["container_request", "properties", "named_store"])
def test_cli_catalogue_rejects_internal_helpers(name):
    with pytest.raises(ValueError, match="Unknown tool"):
        FoxMCPTools.validate_selection([], [name])


@pytest.mark.asyncio
async def test_cli_catalogue_accepts_all_registered_tools():
    frontend = MCPFrontend(BrowserServer(), use_stdio=True)
    try:
        names = [tool.name for tool in await frontend.app.list_tools()]
        FoxMCPTools.validate_selection([], names)
    finally:
        await frontend.close()
