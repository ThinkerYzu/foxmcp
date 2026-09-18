"""
Tests for the native tab-group tools: tabs_group, tabs_ungroup, tab_groups_update
and tab_groups_query

These are the minimal set the maintainer asked for so an agent can move tabs
between groups freely: create/join a group, leave one, restyle one without
regrouping its tabs, and discover a group's ID once it is no longer the one a
call just created.

These tests stub the WebSocket server, so they check the request each tool
builds and the answer it renders — not real Firefox grouping behaviour, which
Firefox enforces in ways no stub can reproduce (pinned tabs, incompatible
windows, the actual rollback of a half-styled group). That belongs to
tests/integration/test_tab_groups_end_to_end.py, which runs these tools against
a real Firefox. The rollback is the one path neither suite reaches: nothing a
caller can pass makes a freshly created group's styling call fail, so it is
covered here by the error branch the extension reports, not by a real failure.
"""

import json
import re
from pathlib import Path

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Stands in for the WebSocket server, recording the request and replaying a canned response

    Tests set `response` to whatever the extension would have sent back, then read
    `sent_request` to check what the tool asked for.
    """

    def __init__(self):
        self.sent_request = None
        self.response = {"type": "response", "data": {}}

    async def send_request_and_wait(self, request):
        self.sent_request = request
        return self.response


@pytest.fixture
def stub_server():
    return StubWebSocketServer()


@pytest.fixture
def call_tool(stub_server):
    """Return a callable that invokes a named MCP tool against the stub server"""
    tools = FoxMCPTools(stub_server)

    async def call(name, **kwargs):
        tool = await tools.mcp.get_tool(name)
        return await tool.fn(**kwargs)

    return call


def group(group_id, title="Research", color="blue", collapsed=False, window_id=1):
    """Build one tab group entry as the extension reports it"""
    return {
        "id": group_id,
        "title": title,
        "color": color,
        "collapsed": collapsed,
        "windowId": window_id,
    }


class TestGroupRequest:
    """What tabs_group puts on the wire"""

    @pytest.mark.asyncio
    async def test_single_id_is_sent_as_a_list(self, call_tool, stub_server):
        await call_tool("tabs_group", tab_ids=12)

        assert stub_server.sent_request["action"] == "tabs.group"
        assert stub_server.sent_request["data"] == {"tabIds": [12]}

    @pytest.mark.asyncio
    async def test_list_of_ids_keeps_its_order(self, call_tool, stub_server):
        await call_tool("tabs_group", tab_ids=[12, 15])

        assert stub_server.sent_request["data"]["tabIds"] == [12, 15]

    @pytest.mark.asyncio
    async def test_json_string_list_is_parsed(self, call_tool, stub_server):
        await call_tool("tabs_group", tab_ids="[12, 15]")

        assert stub_server.sent_request["data"]["tabIds"] == [12, 15]

    @pytest.mark.asyncio
    async def test_string_ids_are_coerced_to_integers(self, call_tool, stub_server):
        await call_tool("tabs_group", tab_ids=["12", "15"])

        assert stub_server.sent_request["data"]["tabIds"] == [12, 15]

    @pytest.mark.asyncio
    async def test_group_id_omitted_when_not_given(self, call_tool, stub_server):
        """Omitting groupId is what tells the extension to create a new group"""
        await call_tool("tabs_group", tab_ids=12)

        assert "groupId" not in stub_server.sent_request["data"]

    @pytest.mark.asyncio
    async def test_group_id_string_is_coerced(self, call_tool, stub_server):
        await call_tool("tabs_group", tab_ids=12, group_id="3")

        assert stub_server.sent_request["data"]["groupId"] == 3

    @pytest.mark.asyncio
    async def test_title_and_color_are_forwarded(self, call_tool, stub_server):
        await call_tool("tabs_group", tab_ids=12, title="Research", color="blue")

        assert stub_server.sent_request["data"]["title"] == "Research"
        assert stub_server.sent_request["data"]["color"] == "blue"

    @pytest.mark.asyncio
    async def test_empty_title_clears_it_rather_than_being_dropped(self, call_tool, stub_server):
        """"" is falsy, so a truthiness check here would silently omit the clear"""
        await call_tool("tabs_group", tab_ids=12, title="")

        assert stub_server.sent_request["data"]["title"] == ""


class TestGroupRejectsBadArguments:
    """Bad input is refused before a request goes out"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs", [
        {"tab_ids": []},
        {"tab_ids": "not json"},
        {"tab_ids": True},
        {"tab_ids": [1.5]},
        {"tab_ids": [-1]},
        {"tab_ids": [None]},
        {"tab_ids": 1, "group_id": -1},
        {"tab_ids": 1, "color": "invalid"},
        {"tab_ids": 1, "title": 3},
    ])
    async def test_invalid_input_does_not_send(self, call_tool, stub_server, kwargs):
        result = await call_tool("tabs_group", **kwargs)

        assert result.startswith("Error:")
        assert stub_server.sent_request is None


class TestGroupResult:
    """What tabs_group reports back"""

    @pytest.mark.asyncio
    async def test_new_group_id_is_reported(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"groupId": 3}}

        result = await call_tool("tabs_group", tab_ids=12)

        assert result == "Tabs grouped into group 3"

    @pytest.mark.asyncio
    async def test_timeout_is_surfaced(self, call_tool, stub_server):
        """send_request_and_wait returns an error dict on timeout rather than raising"""
        stub_server.response = {"error": "Request timed out after 30 seconds"}

        result = await call_tool("tabs_group", tab_ids=12)

        assert "Error grouping tabs" in result
        assert "timed out" in result

    @pytest.mark.asyncio
    async def test_extension_error_is_surfaced(self, call_tool, stub_server):
        """Covers both the ordinary API_ERROR and the rollback message the extension
        sends when styling a newly created group fails — this tool only relays it,
        the rollback itself happens in the extension."""
        stub_server.response = {
            "type": "error",
            "data": {"message": "Tab grouping failed and was rolled back: Group removed"},
        }

        result = await call_tool("tabs_group", tab_ids=12, color="blue")

        assert "Failed to group tabs" in result
        assert "rolled back" in result

    @pytest.mark.asyncio
    async def test_unexpected_shape_falls_back(self, call_tool, stub_server):
        stub_server.response = {}

        result = await call_tool("tabs_group", tab_ids=12)

        assert result == "Unable to group tabs"


class TestUngroupRequest:
    """What tabs_ungroup puts on the wire"""

    @pytest.mark.asyncio
    async def test_single_id_is_sent_as_a_list(self, call_tool, stub_server):
        await call_tool("tabs_ungroup", tab_ids=12)

        assert stub_server.sent_request["action"] == "tabs.ungroup"
        assert stub_server.sent_request["data"] == {"tabIds": [12]}

    @pytest.mark.asyncio
    async def test_list_of_ids_keeps_its_order(self, call_tool, stub_server):
        await call_tool("tabs_ungroup", tab_ids=[12, 15])

        assert stub_server.sent_request["data"]["tabIds"] == [12, 15]

    @pytest.mark.asyncio
    async def test_json_string_list_is_parsed(self, call_tool, stub_server):
        await call_tool("tabs_ungroup", tab_ids="[12, 15]")

        assert stub_server.sent_request["data"]["tabIds"] == [12, 15]

    @pytest.mark.asyncio
    async def test_string_ids_are_coerced_to_integers(self, call_tool, stub_server):
        await call_tool("tabs_ungroup", tab_ids="12")

        assert stub_server.sent_request["data"]["tabIds"] == [12]


class TestUngroupRejectsBadArguments:
    """Bad input is refused before a request goes out"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs", [
        {"tab_ids": []},
        {"tab_ids": "not json"},
        {"tab_ids": True},
        {"tab_ids": [-1]},
        {"tab_ids": [1.5]},
    ])
    async def test_invalid_input_does_not_send(self, call_tool, stub_server, kwargs):
        result = await call_tool("tabs_ungroup", **kwargs)

        assert result.startswith("Error:")
        assert stub_server.sent_request is None


class TestUngroupResult:
    """What tabs_ungroup reports back"""

    @pytest.mark.asyncio
    async def test_success_names_how_many(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"success": True}}

        result = await call_tool("tabs_ungroup", tab_ids=[12, 15])

        assert result == "Ungrouped 2 tab(s)"

    @pytest.mark.asyncio
    async def test_timeout_is_surfaced(self, call_tool, stub_server):
        stub_server.response = {"error": "Request timed out after 30 seconds"}

        result = await call_tool("tabs_ungroup", tab_ids=12)

        assert "Error ungrouping tabs" in result

    @pytest.mark.asyncio
    async def test_extension_error_is_surfaced(self, call_tool, stub_server):
        stub_server.response = {"type": "error", "data": {"message": "Unsupported API"}}

        result = await call_tool("tabs_ungroup", tab_ids=12)

        assert "Failed to ungroup tabs" in result
        assert "Unsupported API" in result

    @pytest.mark.asyncio
    async def test_unexpected_shape_falls_back(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {}}

        result = await call_tool("tabs_ungroup", tab_ids=12)

        assert result == "Unable to ungroup tabs"


class TestGroupsUpdateRequest:
    """What tab_groups_update puts on the wire"""

    @pytest.mark.asyncio
    async def test_group_id_is_required_on_the_wire(self, call_tool, stub_server):
        await call_tool("tab_groups_update", group_id=3, title="Research")

        assert stub_server.sent_request["action"] == "tabGroups.update"
        assert stub_server.sent_request["data"] == {"groupId": 3, "title": "Research"}

    @pytest.mark.asyncio
    async def test_group_id_string_is_coerced(self, call_tool, stub_server):
        await call_tool("tab_groups_update", group_id="3", color="blue")

        assert stub_server.sent_request["data"]["groupId"] == 3

    @pytest.mark.asyncio
    async def test_collapsed_false_is_sent_not_dropped(self, call_tool, stub_server):
        """False is falsy, so a truthiness check here would silently omit it"""
        await call_tool("tab_groups_update", group_id=3, collapsed=False)

        assert stub_server.sent_request["data"]["collapsed"] is False

    @pytest.mark.asyncio
    async def test_all_three_properties_are_forwarded_together(self, call_tool, stub_server):
        await call_tool(
            "tab_groups_update", group_id=3, title="Research", color="blue", collapsed=True
        )

        assert stub_server.sent_request["data"] == {
            "groupId": 3, "title": "Research", "color": "blue", "collapsed": True,
        }


class TestGroupsUpdateRejectsBadArguments:
    """Bad input is refused before a request goes out"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs", [
        {"group_id": 3},  # none of title/color/collapsed given
        {"group_id": -1, "title": "x"},
        {"group_id": True, "title": "x"},
        {"group_id": 3, "title": 1},
        {"group_id": 3, "color": "invalid"},
        {"group_id": 3, "collapsed": "yes"},
    ])
    async def test_invalid_input_does_not_send(self, call_tool, stub_server, kwargs):
        result = await call_tool("tab_groups_update", **kwargs)

        assert result.startswith("Error:")
        assert stub_server.sent_request is None


class TestGroupsUpdateResult:
    """What tab_groups_update reports back"""

    @pytest.mark.asyncio
    async def test_success_names_the_group(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"group": group(3)}}

        result = await call_tool("tab_groups_update", group_id=3, title="Research")

        assert result == "Updated group 3"

    @pytest.mark.asyncio
    async def test_timeout_is_surfaced(self, call_tool, stub_server):
        stub_server.response = {"error": "Request timed out after 30 seconds"}

        result = await call_tool("tab_groups_update", group_id=3, title="Research")

        assert "Error updating group" in result

    @pytest.mark.asyncio
    async def test_extension_error_is_surfaced(self, call_tool, stub_server):
        stub_server.response = {"type": "error", "data": {"message": "No group with id 3"}}

        result = await call_tool("tab_groups_update", group_id=3, title="Research")

        assert "Failed to update group" in result
        assert "No group with id 3" in result

    @pytest.mark.asyncio
    async def test_unexpected_shape_falls_back(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {}}

        result = await call_tool("tab_groups_update", group_id=3, title="Research")

        assert result == "Unable to update group"


class TestGroupsQueryRequest:
    """What tab_groups_query puts on the wire — only the filters actually given"""

    @pytest.mark.asyncio
    async def test_no_filters_sends_an_empty_query(self, call_tool, stub_server):
        await call_tool("tab_groups_query")

        assert stub_server.sent_request["action"] == "tabGroups.query"
        assert stub_server.sent_request["data"] == {}

    @pytest.mark.asyncio
    async def test_window_id_string_is_coerced(self, call_tool, stub_server):
        await call_tool("tab_groups_query", window_id="7")

        assert stub_server.sent_request["data"]["windowId"] == 7

    @pytest.mark.asyncio
    async def test_collapsed_false_is_sent_not_dropped(self, call_tool, stub_server):
        await call_tool("tab_groups_query", collapsed=False)

        assert stub_server.sent_request["data"]["collapsed"] is False

    @pytest.mark.asyncio
    async def test_every_filter_together(self, call_tool, stub_server):
        await call_tool(
            "tab_groups_query", window_id=7, title="Research", color="blue", collapsed=True
        )

        assert stub_server.sent_request["data"] == {
            "windowId": 7, "title": "Research", "color": "blue", "collapsed": True,
        }


class TestGroupsQueryRejectsBadArguments:
    """Bad input is refused before a request goes out"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs", [
        {"window_id": "not a number"},
        {"window_id": -1},
        {"title": 1},
        {"color": "invalid"},
        {"collapsed": "yes"},
    ])
    async def test_invalid_input_does_not_send(self, call_tool, stub_server, kwargs):
        result = await call_tool("tab_groups_query", **kwargs)

        assert result.startswith("Error:")
        assert stub_server.sent_request is None


class TestGroupsQueryResult:
    """What tab_groups_query reports back — IDs must be easy to read out"""

    @pytest.mark.asyncio
    async def test_group_ids_are_readable_in_the_listing(self, call_tool, stub_server):
        """Discovering IDs is the whole point of this tool, per the maintainer's request"""
        stub_server.response = {
            "type": "response",
            "data": {"groups": [group(3, title="Research", color="blue", window_id=1)]},
        }

        result = await call_tool("tab_groups_query")

        assert "ID 3" in result
        assert "Research" in result
        assert "blue" in result
        assert "[window 1]" in result

    @pytest.mark.asyncio
    async def test_id_stays_parsable_from_the_listing(self, call_tool, stub_server):
        """Mirrors the `ID (\\d+):` convention tabs_list uses, for the same reason"""
        stub_server.response = {"type": "response", "data": {"groups": [group(3)]}}

        result = await call_tool("tab_groups_query")

        assert re.search(r"ID (\d+):", result).group(1) == "3"

    @pytest.mark.asyncio
    async def test_collapsed_group_is_marked(self, call_tool, stub_server):
        stub_server.response = {
            "type": "response",
            "data": {"groups": [group(3, collapsed=True)]},
        }

        result = await call_tool("tab_groups_query")

        assert "(collapsed)" in result

    @pytest.mark.asyncio
    async def test_untitled_group_does_not_render_as_blank(self, call_tool, stub_server):
        stub_server.response = {
            "type": "response",
            "data": {"groups": [group(3, title="")]},
        }

        result = await call_tool("tab_groups_query")

        assert "Untitled" in result

    @pytest.mark.asyncio
    async def test_no_groups_found(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"groups": []}}

        result = await call_tool("tab_groups_query")

        assert result == "No tab groups found"

    @pytest.mark.asyncio
    async def test_timeout_is_surfaced(self, call_tool, stub_server):
        stub_server.response = {"error": "Request timed out after 30 seconds"}

        result = await call_tool("tab_groups_query")

        assert "Error listing groups" in result

    @pytest.mark.asyncio
    async def test_extension_error_is_surfaced(self, call_tool, stub_server):
        stub_server.response = {"type": "error", "data": {"message": "Unsupported API"}}

        result = await call_tool("tab_groups_query")

        assert "Failed to list groups" in result
        assert "Unsupported API" in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("response", [
        {},
        {"type": "response", "data": {}},
    ])
    async def test_unexpected_shape_falls_back(self, call_tool, stub_server, response):
        """A reply carrying no `groups` at all is a broken answer, not an empty one -
        reporting "No tab groups found" for it would invent a fact about the browser"""
        stub_server.response = response

        result = await call_tool("tab_groups_query")

        assert result == "Unable to list groups"


def test_manifest_declares_the_tabgroups_permission():
    """Cheap and legitimate: every tool in this file is unusable without it"""
    manifest = json.loads(
        (Path(__file__).resolve().parents[2] / "extension/manifest.json").read_text()
    )
    assert "tabGroups" in manifest["permissions"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
