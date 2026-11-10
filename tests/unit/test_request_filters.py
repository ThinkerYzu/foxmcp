"""Tests for filtering the request summaries requests_list_captured returns"""

import json

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Replays a canned list of captured requests"""

    def __init__(self):
        self.response = {"type": "response", "data": {
            "monitor_id": "m", "total_requests": 4, "requests": [
                {"url": "https://example.org/a.js", "method": "GET", "status_code": 200, "type": "script"},
                {"url": "https://example.org/api/save", "method": "POST", "status_code": 500,
                 "type": "xmlhttprequest"},
                {"url": "https://example.org/api/list", "method": "GET", "status_code": 200,
                 "type": "xmlhttprequest"},
                {"url": "https://example.org/b.png", "method": "GET", "status_code": 0, "type": "image",
                 "error": "NS_ERROR"}]}}

    async def send_request_and_wait(self, request, timeout=30.0):
        return self.response


@pytest.fixture
def listed():
    tools = FoxMCPTools(StubWebSocketServer())

    async def call(**filters):
        tool = await tools.mcp.get_tool("requests_list_captured")
        return json.loads(await tool.fn(profile_id=1, monitor_id="m", **filters))

    return call


class TestRequestFilters:

    @pytest.mark.asyncio
    async def test_without_filters_nothing_is_dropped(self, listed):
        data = await listed()

        assert len(data["requests"]) == 4
        assert "matched_requests" not in data

    @pytest.mark.asyncio
    async def test_filters_combine(self, listed):
        data = await listed(url_contains="/api/", method="get")

        assert [r["url"] for r in data["requests"]] == ["https://example.org/api/list"]
        assert data["matched_requests"] == 1
        assert data["total_requests"] == 4

    @pytest.mark.asyncio
    async def test_resource_type_and_minimum_status(self, listed):
        by_type = await listed(resource_type="image")
        by_status = await listed(min_status=500)

        assert [r["type"] for r in by_type["requests"]] == ["image"]
        assert [r["status_code"] for r in by_status["requests"]] == [500]

    @pytest.mark.asyncio
    async def test_failed_only_includes_errors_and_bad_statuses(self, listed):
        data = await listed(failed_only=True)

        assert [r["type"] for r in data["requests"]] == ["xmlhttprequest", "image"]

    @pytest.mark.asyncio
    async def test_limit_keeps_the_newest(self, listed):
        data = await listed(limit=1)

        assert [r["type"] for r in data["requests"]] == ["image"]
