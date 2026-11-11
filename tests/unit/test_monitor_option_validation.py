"""Capture options must be discoverable and reject malformed values before I/O."""

import json

import pytest
from fastmcp import Client

import test_imports  # noqa: F401
from server.mcp_tools import FoxMCPTools


class Browser:
    def __init__(self):
        self.requests = []

    async def send_request_and_wait(self, request, timeout=30):
        self.requests.append(request)
        return {"type": "response", "data": {
            "monitor_id": "mon_test", "status": "active", "options": request["data"]["options"]}}


INVALID_OPTIONS = [
    {"capture_request_bodies": "false"},
    {"capture_request_bodies": 0},
    {"capture_response_bodies": "false"},
    {"capture_response_bodies": 1},
    {"max_body_size": 0},
    {"max_body_size": -1},
    {"max_body_size": True},
    {"max_body_size": 1.5},
    {"max_body_size": "100"},
    {"content_types_to_capture": "text/plain"},
    {"content_types_to_capture": [1]},
    {"content_types_to_capture": [""]},
    {"sensitive_headers": ["Cookie"]},
    {"method": "POST"},
    {"unknown": True},
]


@pytest.mark.asyncio
@pytest.mark.parametrize("options", INVALID_OPTIONS)
async def test_mcp_rejects_invalid_capture_options_before_browser_call(options):
    browser = Browser()
    tools = FoxMCPTools(browser)
    async with Client(tools.mcp) as client:
        with pytest.raises(Exception, match="validation|Validation"):
            await client.call_tool("requests_start_monitoring", {
                "profile_id": 1, "url_patterns": ["https://example.org/*"], "options": options})
    assert browser.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("options", INVALID_OPTIONS + [False, 0, [], "bad"])
async def test_direct_call_also_validates_capture_options(options):
    browser = Browser()
    tool = await FoxMCPTools(browser).mcp.get_tool("requests_start_monitoring")
    result = json.loads(await tool.fn(
        profile_id=1, url_patterns=["https://example.org/*"], options=options))
    assert "Invalid monitoring options" in result["error"]
    assert browser.requests == []


@pytest.mark.asyncio
async def test_schema_exposes_options_and_defaults_are_not_shared():
    browser = Browser()
    tools = FoxMCPTools(browser)
    async with Client(tools.mcp) as client:
        tool = next(t for t in await client.list_tools() if t.name == "requests_start_monitoring")
        definition = next(d for d in tool.inputSchema["properties"]["options"]["anyOf"]
                          if "capture_request_bodies" in d.get("properties", {}))
        assert definition["additionalProperties"] is False
        assert set(definition["properties"]) == {
            "capture_request_bodies", "capture_response_bodies", "max_body_size",
            "content_types_to_capture"}
        await client.call_tool("requests_start_monitoring", {
            "profile_id": 1, "url_patterns": ["https://example.org/*"],
            "options": {"capture_request_bodies": False, "content_types_to_capture": []}})
        await client.call_tool("requests_start_monitoring", {
            "profile_id": 1, "url_patterns": ["https://example.org/*"]})
    first, second = [r["data"]["options"] for r in browser.requests]
    assert first == {"capture_request_bodies": False, "capture_response_bodies": True,
                     "max_body_size": 50000, "content_types_to_capture": []}
    assert second == {"capture_request_bodies": True, "capture_response_bodies": True,
                      "max_body_size": 50000,
                      "content_types_to_capture": ["application/json", "text/plain"]}
