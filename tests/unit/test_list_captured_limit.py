"""The limit argument of requests_list_captured"""

import json

import pytest
from fastmcp import Client

import test_imports  # noqa: F401
from server.mcp_tools import FoxMCPTools


class Browser:
    def __init__(self):
        self.sent = 0
        self.response = {"type": "response", "data": {
            "monitor_id": "m", "total_requests": 3, "requests": [
                {"request_id": "1", "url": "https://example.org/a"},
                {"request_id": "2", "url": "https://example.org/b"},
                {"request_id": "3", "url": "https://example.org/c"}]}}

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent += 1
        return self.response


@pytest.fixture
def browser():
    return Browser()


@pytest.fixture
def listed(browser):
    async def call(**arguments):
        tool = await FoxMCPTools(browser).mcp.get_tool("requests_list_captured")
        return json.loads(await tool.fn(profile_id=1, monitor_id="m", **arguments))

    return call


@pytest.mark.asyncio
async def test_without_limit_everything_is_returned_unchanged(listed):
    data = await listed()

    assert [r["request_id"] for r in data["requests"]] == ["1", "2", "3"]
    assert "returned_requests" not in data


@pytest.mark.asyncio
async def test_limit_keeps_the_last_requests_captured(listed):
    data = await listed(limit=2)

    assert [r["request_id"] for r in data["requests"]] == ["2", "3"]
    assert data["returned_requests"] == 2
    assert data["total_requests"] == 3


@pytest.mark.asyncio
async def test_a_limit_above_the_count_returns_everything(listed):
    data = await listed(limit=50)

    assert data["returned_requests"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "2"])
async def test_a_bad_limit_is_refused_before_anything_is_sent(listed, browser, limit):
    data = await listed(limit=limit)

    assert data == {"error": "limit must be an integer of 1 or more"}
    assert browser.sent == 0


@pytest.mark.asyncio
async def test_a_response_without_a_list_is_an_error_when_limiting(listed, browser):
    browser.response = {"type": "response", "data": {"monitor_id": "m"}}

    data = await listed(limit=1)

    assert "no request list" in data["error"]


@pytest.mark.asyncio
async def test_extension_errors_still_come_through(listed, browser):
    browser.response = {"type": "error", "data": {"message": "Monitor m not found"}}

    data = await listed(limit=1)

    assert data == {"error": "Failed to list captured requests: Monitor m not found"}


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [True, "5", 0, -1, 1.5])
async def test_the_mcp_layer_rejects_a_lax_limit(browser, limit):
    async with Client(FoxMCPTools(browser).mcp) as client:
        with pytest.raises(Exception, match="validation|Validation"):
            await client.call_tool("requests_list_captured", {
                "profile_id": 1, "monitor_id": "m", "limit": limit})
    assert browser.sent == 0