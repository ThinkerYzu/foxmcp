"""Tests for content_list_downloads and content_wait_download"""

import json
from pathlib import Path

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Records the request and replays a canned response"""

    def __init__(self):
        self.sent_request = None
        self.timeout = None
        self.response = {"type": "response", "data": {}}

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent_request = request
        self.timeout = timeout
        return self.response


@pytest.fixture
def stub_server():
    return StubWebSocketServer()


@pytest.fixture
def call_tool(stub_server):
    tools = FoxMCPTools(stub_server)

    async def call(name, **kwargs):
        tool = await tools.mcp.get_tool(name)
        return await tool.fn(**kwargs)

    return call


EXPORT = {"id": 7, "filename": "/home/u/Downloads/export.csv", "state": "complete",
          "bytes": 120, "url": "https://example.org/export.csv", "error": None}


class TestListDownloads:

    @pytest.mark.asyncio
    async def test_lists_the_saved_files(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"downloads": [EXPORT]}}

        result = await call_tool("content_list_downloads", profile_id=1, limit=3)

        assert stub_server.sent_request["action"] == "content.list_downloads"
        assert stub_server.sent_request["data"] == {"limit": 3}
        assert result == ("- [7] /home/u/Downloads/export.csv (complete, 120 bytes) "
                          "from https://example.org/export.csv")

    @pytest.mark.asyncio
    async def test_says_when_there_are_none(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"downloads": []}}

        assert await call_tool("content_list_downloads", profile_id=1) == "No downloads"

    @pytest.mark.asyncio
    async def test_failed_downloads_show_their_error(self, call_tool, stub_server):
        failed = {**EXPORT, "state": "interrupted", "error": "NETWORK_FAILED"}
        stub_server.response = {"type": "response", "data": {"downloads": [failed]}}

        result = await call_tool("content_list_downloads", profile_id=1)

        assert result.endswith(" - error: NETWORK_FAILED")


class TestWaitDownload:

    @pytest.mark.asyncio
    async def test_returns_the_finished_download(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"download": EXPORT}}

        result = await call_tool("content_wait_download", profile_id=1, timeout=60)

        assert stub_server.sent_request["action"] == "content.wait_download"
        assert stub_server.sent_request["data"] == {"timeoutMs": 60000}
        assert stub_server.timeout > 60.0
        assert result.startswith("- [7] /home/u/Downloads/export.csv (complete")

    @pytest.mark.asyncio
    async def test_reports_a_download_that_never_comes(self, call_tool, stub_server):
        stub_server.response = {"type": "error", "data": {
            "message": "No download finished within 1000 ms"}}

        result = await call_tool("content_wait_download", profile_id=1, timeout=1)

        assert result == "Failed to wait for a download: No download finished within 1000 ms"


class TestArguments:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("limit", [0, -1, 101, True, 2.5, "3"])
    async def test_limit_must_be_an_integer_from_1_to_100(self, call_tool, stub_server, limit):
        result = await call_tool("content_list_downloads", profile_id=1, limit=limit)

        assert result == "Failed to list downloads: limit must be an integer from 1 to 100"
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("timeout", [0, -5, 301, True, "5", float("nan"), float("inf")])
    async def test_timeout_must_be_above_zero_and_at_most_300(self, call_tool, stub_server, timeout):
        result = await call_tool("content_wait_download", profile_id=1, timeout=timeout)

        assert result == ("Failed to wait for a download: "
                          "timeout must be a number above 0 and at most 300")
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_extension_rejection_is_reported(self, call_tool, stub_server):
        stub_server.response = {"type": "error", "data": {
            "code": "INVALID_PARAMETER", "message": "limit must be an integer from 1 to 100"}}

        result = await call_tool("content_list_downloads", profile_id=1)

        assert result == "Failed to list downloads: limit must be an integer from 1 to 100"


def test_manifest_asks_for_the_downloads_permission():
    manifest = json.loads(
        (Path(__file__).resolve().parents[2] / "extension/manifest.json").read_text())

    assert "downloads" in manifest["permissions"]