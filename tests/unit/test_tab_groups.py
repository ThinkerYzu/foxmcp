"""Tab-group wire contract, with no browser or network connection."""
import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import test_imports
from server.mcp_tools import FoxMCPTools


@pytest.fixture
def stub():
    server = AsyncMock()
    server.send_request_and_wait.return_value = {"type": "response", "data": {"groupId": 0}}
    return server


@pytest.mark.asyncio
@pytest.mark.parametrize("ids", [12, "12", [12], '["12"]'])
async def test_create_group(stub, ids):
    tool = await FoxMCPTools(stub).mcp.get_tool("tabs_group")
    assert await tool.fn(ids, title="Research", color="blue") == "Tabs grouped into group 0"
    request = stub.send_request_and_wait.call_args.args[0]
    assert request["action"] == "tabs.group"
    assert request["data"] == {"tabIds": [12], "title": "Research", "color": "blue"}


@pytest.mark.asyncio
async def test_existing_group_and_defaults(stub):
    tool = await FoxMCPTools(stub).mcp.get_tool("tabs_group")
    await tool.fn([12, 15], group_id="0")
    assert stub.send_request_and_wait.call_args.args[0]["data"] == {
        "tabIds": [12, 15], "groupId": 0}
    await tool.fn(12, title="")
    assert stub.send_request_and_wait.call_args.args[0]["data"]["title"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [
    {"tab_ids": []}, {"tab_ids": "bad"}, {"tab_ids": True},
    {"tab_ids": [1.5]}, {"tab_ids": [-1]}, {"tab_ids": [None]},
    {"tab_ids": 1, "group_id": -1}, {"tab_ids": 1, "color": "invalid"},
    {"tab_ids": 1, "title": 3},
])
async def test_invalid_input_does_not_send(stub, kwargs):
    tool = await FoxMCPTools(stub).mcp.get_tool("tabs_group")
    assert (await tool.fn(**kwargs)).startswith("Error:")
    stub.send_request_and_wait.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("response, expected", [
    ({"error": "Disconnected"}, "Disconnected"),
    ({"type": "error", "data": {"message": "Unsupported API"}}, "Unsupported API"),
    ({"type": "error", "data": {"message": "Tabs grouped into group 7, but styling failed"}}, "group 7"),
    ({}, "Unable to group tabs"),
])
async def test_errors(stub, response, expected):
    stub.send_request_and_wait.return_value = response
    tool = await FoxMCPTools(stub).mcp.get_tool("tabs_group")
    assert expected in await tool.fn(1)


def test_extension_handler():
    """Run the actual handler in a Node VM with only mocked browser APIs."""
    root = Path(__file__).resolve().parents[2]
    subprocess.run(["node", "--test", str(root / "tests/unit/tab_groups.test.cjs")], check=True)
    assert "tabGroups" in json.loads((root / "extension/manifest.json").read_text())["permissions"]
