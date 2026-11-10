"""Tests for filtering the request summaries requests_list_captured returns"""

import json

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Replays a canned list of captured requests"""

    def __init__(self):
        self.sent = 0
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
        self.sent += 1
        return self.response


@pytest.fixture
def stub():
    return StubWebSocketServer()


@pytest.fixture
def listed(stub):
    tools = FoxMCPTools(stub)

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

    @pytest.mark.asyncio
    async def test_limit_of_zero_is_refused_not_ignored(self, listed, stub):
        data = await listed(limit=0)

        assert data == {"error": "limit must be an integer of 1 or more"}
        assert stub.sent == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("filters, message", [
        ({"limit": -1}, "limit must be an integer of 1 or more"),
        ({"limit": True}, "limit must be an integer of 1 or more"),
        ({"limit": 1.5}, "limit must be an integer of 1 or more"),
        ({"min_status": 0}, "min_status must be an integer from 100 to 599"),
        ({"min_status": 600}, "min_status must be an integer from 100 to 599"),
        ({"min_status": True}, "min_status must be an integer from 100 to 599"),
        ({"min_status": "500"}, "min_status must be an integer from 100 to 599"),
        ({"url_contains": 5}, "url_contains must be a string"),
        ({"method": ["GET"]}, "method must be a string"),
        ({"resource_type": 1}, "resource_type must be a string"),
        ({"failed_only": 1}, "failed_only must be a boolean"),
    ])
    async def test_invalid_filters_are_refused_before_anything_is_sent(
            self, listed, stub, filters, message):
        data = await listed(**filters)

        assert data == {"error": message}
        assert stub.sent == 0

    @pytest.mark.asyncio
    async def test_a_response_without_a_list_is_an_error_when_filtering(self, listed, stub):
        stub.response = {"type": "response", "data": {"monitor_id": "m"}}

        data = await listed(method="GET")

        assert "no request list" in data["error"]

    @pytest.mark.asyncio
    async def test_failed_only_ignores_status_zero_without_an_error(self, listed):
        data = await listed(failed_only=True, resource_type="script")

        assert data["requests"] == []
        assert data["matched_requests"] == 0