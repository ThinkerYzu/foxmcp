"""Capture filters of requests_start_monitoring: validation, and what is sent to the extension"""

import json

import pytest

import test_imports  # noqa: F401
from server.mcp_tools import FoxMCPTools

BASE_OPTIONS = {
    "capture_request_bodies": True, "capture_response_bodies": True,
    "max_body_size": 50000, "content_types_to_capture": ["application/json", "text/plain"]}


class Browser:
    def __init__(self):
        self.requests = []

    async def send_request_and_wait(self, request, timeout=30):
        self.requests.append(request)
        return {"type": "response", "data": {
            "monitor_id": "mon_test", "status": "active", "options": request["data"]["options"]}}


async def start(browser, options=None):
    tool = await FoxMCPTools(browser).mcp.get_tool("requests_start_monitoring")
    return json.loads(await tool.fn(
        profile_id=1, url_patterns=["https://example.org/*"], options=options))


@pytest.mark.asyncio
async def test_without_filters_the_extension_gets_the_options_it_always_got():
    browser = Browser()

    await start(browser)

    assert browser.requests[0]["data"]["options"] == BASE_OPTIONS


@pytest.mark.asyncio
async def test_empty_or_default_filters_are_not_sent():
    browser = Browser()

    await start(browser, {"methods": [], "resource_types": [], "min_status": None,
                          "failed_only": False})

    assert browser.requests[0]["data"]["options"] == BASE_OPTIONS


@pytest.mark.asyncio
async def test_filters_that_are_set_are_sent():
    browser = Browser()

    await start(browser, {"methods": ["POST"], "resource_types": ["xmlhttprequest"],
                          "min_status": 400, "failed_only": True})

    assert browser.requests[0]["data"]["options"] == {
        **BASE_OPTIONS, "methods": ["POST"], "resource_types": ["xmlhttprequest"],
        "min_status": 400, "failed_only": True}


@pytest.mark.asyncio
async def test_a_filter_can_be_set_on_its_own():
    browser = Browser()

    await start(browser, {"failed_only": True})

    assert browser.requests[0]["data"]["options"] == {**BASE_OPTIONS, "failed_only": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("options", [
    {"methods": "POST"},
    {"methods": [""]},
    {"methods": [1]},
    {"resource_types": "script"},
    {"resource_types": [""]},
    {"resource_types": [None]},
    {"min_status": 99},
    {"min_status": 600},
    {"min_status": True},
    {"min_status": 400.5},
    {"min_status": "500"},
    {"failed_only": 1},
    {"failed_only": "yes"},
    {"method": "POST"},
])
async def test_invalid_filters_are_refused_before_anything_is_sent(options):
    browser = Browser()

    result = await start(browser, options)

    assert "Invalid monitoring options" in result["error"]
    assert browser.requests == []
