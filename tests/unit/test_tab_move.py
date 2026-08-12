"""
Tests for moving tabs and for listing the tabs of one window

tabs_move exists to serve one scenario: gather tabs into a window of their own.
That takes both halves of this file — tabs_list has to report which window each
tab is in and where it sits, and tabs_move has to accept the IDs it turns up.

These tests stub the WebSocket server, so they check the request the tool builds
and the answer it renders, not the browser's behavior. The move itself is covered
against real Firefox in tests/integration/test_tab_move_end_to_end.py.
"""

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
        self.response = {"type": "response", "data": {"tabs": []}}

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


def tab(tab_id, window_id=1, index=0, title="A tab", url="https://example.org/"):
    """Build one tab entry as the extension reports it"""
    return {
        "id": tab_id,
        "url": url,
        "title": title,
        "active": False,
        "windowId": window_id,
        "pinned": False,
        "index": index,
    }


class TestMoveRequest:
    """What tabs_move puts on the wire"""

    @pytest.mark.asyncio
    async def test_single_id_is_sent_as_a_list(self, call_tool, stub_server):
        """The extension always receives an array, whatever the caller passed"""
        await call_tool("tabs_move", tab_ids=12)

        assert stub_server.sent_request["action"] == "tabs.move"
        assert stub_server.sent_request["data"]["tabIds"] == [12]

    @pytest.mark.asyncio
    async def test_list_of_ids_keeps_its_order(self, call_tool, stub_server):
        await call_tool("tabs_move", tab_ids=[12, 15, 3])

        assert stub_server.sent_request["data"]["tabIds"] == [12, 15, 3]

    @pytest.mark.asyncio
    async def test_json_string_list_is_parsed(self, call_tool, stub_server):
        """MCP clients that cannot send arrays pass a JSON string instead"""
        await call_tool("tabs_move", tab_ids="[12, 15]")

        assert stub_server.sent_request["data"]["tabIds"] == [12, 15]

    @pytest.mark.asyncio
    async def test_string_ids_are_coerced_to_integers(self, call_tool, stub_server):
        await call_tool("tabs_move", tab_ids=["12", "15"])

        assert stub_server.sent_request["data"]["tabIds"] == [12, 15]

    @pytest.mark.asyncio
    async def test_index_defaults_to_the_end(self, call_tool, stub_server):
        await call_tool("tabs_move", tab_ids=12)

        assert stub_server.sent_request["data"]["index"] == -1

    @pytest.mark.asyncio
    async def test_index_zero_is_sent_not_dropped(self, call_tool, stub_server):
        """0 is falsy, so a truthiness check here would silently move tabs to the end"""
        await call_tool("tabs_move", tab_ids=12, index=0)

        assert stub_server.sent_request["data"]["index"] == 0

    @pytest.mark.asyncio
    async def test_window_id_is_omitted_when_not_given(self, call_tool, stub_server):
        """Without a windowId the browser reorders within each tab's current window"""
        await call_tool("tabs_move", tab_ids=12)

        assert "windowId" not in stub_server.sent_request["data"]

    @pytest.mark.asyncio
    async def test_window_id_string_is_coerced(self, call_tool, stub_server):
        await call_tool("tabs_move", tab_ids=12, window_id="7")

        assert stub_server.sent_request["data"]["windowId"] == 7


class TestMoveRejectsBadArguments:
    """Bad input is refused before a request goes out"""

    @pytest.mark.asyncio
    async def test_unparsable_tab_ids_string(self, call_tool, stub_server):
        result = await call_tool("tabs_move", tab_ids="not json")

        assert "Error" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_non_numeric_tab_id(self, call_tool, stub_server):
        result = await call_tool("tabs_move", tab_ids=[12, "abc"])

        assert "Invalid tab ID" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_empty_list(self, call_tool, stub_server):
        result = await call_tool("tabs_move", tab_ids=[])

        assert "empty" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_non_numeric_window_id(self, call_tool, stub_server):
        result = await call_tool("tabs_move", tab_ids=12, window_id="left one")

        assert "Invalid window_id" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_index_below_minus_one(self, call_tool, stub_server):
        """browser.tabs.move throws on an index under -1; catch it before the round trip"""
        result = await call_tool("tabs_move", tab_ids=12, index=-2)

        assert "Invalid index" in result
        assert stub_server.sent_request is None


class TestMoveResult:
    """What tabs_move reports back"""

    @pytest.mark.asyncio
    async def test_moved_tabs_report_their_destination(self, call_tool, stub_server):
        stub_server.response = {
            "type": "response",
            "data": {
                "tabs": [tab(12, window_id=7, index=0), tab(15, window_id=7, index=1)],
                "requested": 2,
                "moved": 2,
            },
        }

        result = await call_tool("tabs_move", tab_ids=[12, 15], window_id=7)

        assert "Moved 2 of 2" in result
        assert "ID 12 -> window 7, index 0" in result
        assert "ID 15 -> window 7, index 1" in result

    @pytest.mark.asyncio
    async def test_silent_refusal_is_reported_as_a_failure(self, call_tool, stub_server):
        """An empty tab list means Firefox declined the move without raising"""
        stub_server.response = {"type": "response", "data": {"tabs": [], "requested": 1, "moved": 0}}

        result = await call_tool("tabs_move", tab_ids=12, index=0)

        assert "No tabs moved" in result
        assert "pinned" in result

    @pytest.mark.asyncio
    async def test_partial_move_shows_both_counts(self, call_tool, stub_server):
        """Asking for three and getting one back has to read as a partial result"""
        stub_server.response = {
            "type": "response",
            "data": {"tabs": [tab(12, index=3)], "requested": 3, "moved": 1},
        }

        result = await call_tool("tabs_move", tab_ids=[12, 15, 3])

        assert "Moved 1 of 3" in result

    @pytest.mark.asyncio
    async def test_extension_error_is_surfaced(self, call_tool, stub_server):
        stub_server.response = {
            "type": "error",
            "data": {"message": "Tabs API error: Invalid tab ID: 999"},
        }

        result = await call_tool("tabs_move", tab_ids=999)

        assert "Failed to move tabs" in result
        assert "Invalid tab ID: 999" in result

    @pytest.mark.asyncio
    async def test_timeout_is_surfaced(self, call_tool, stub_server):
        """send_request_and_wait returns an error dict on timeout rather than raising"""
        stub_server.response = {"error": "Request timed out after 30 seconds"}

        result = await call_tool("tabs_move", tab_ids=12)

        assert "Error moving tabs" in result
        assert "timed out" in result


class TestTabsListScope:
    """Which window tabs_list asks about, and what it reports"""

    @pytest.mark.asyncio
    async def test_no_window_id_asks_for_every_window(self, call_tool, stub_server):
        """An absent windowId is what tells the extension to query all windows"""
        stub_server.response = {"type": "response", "data": {"tabs": [tab(1)]}}

        await call_tool("tabs_list")

        assert "windowId" not in stub_server.sent_request["data"]

    @pytest.mark.asyncio
    async def test_window_id_scopes_the_query(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"tabs": [tab(1, window_id=7)]}}

        result = await call_tool("tabs_list", window_id=7)

        assert stub_server.sent_request["data"]["windowId"] == 7
        assert "in window 7" in result

    @pytest.mark.asyncio
    async def test_window_id_string_is_coerced(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"tabs": [tab(1, window_id=7)]}}

        await call_tool("tabs_list", window_id="7")

        assert stub_server.sent_request["data"]["windowId"] == 7

    @pytest.mark.asyncio
    async def test_non_numeric_window_id_is_refused(self, call_tool, stub_server):
        result = await call_tool("tabs_list", window_id="the other one")

        assert "Invalid window_id" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_listing_reports_window_and_index(self, call_tool, stub_server):
        """Both are needed to plan a move, and neither used to be shown"""
        stub_server.response = {
            "type": "response",
            "data": {"tabs": [tab(12, window_id=3, index=5, title="Amazon")]},
        }

        result = await call_tool("tabs_list")

        assert "[window 3, index 5]" in result

    @pytest.mark.asyncio
    async def test_tab_id_stays_parsable_from_the_listing(self, call_tool, stub_server):
        """Callers pull IDs out with an `ID (\\d+):` pattern, so keep the colon adjacent"""
        import re

        stub_server.response = {
            "type": "response",
            "data": {"tabs": [tab(12, window_id=3, index=5)]},
        }

        result = await call_tool("tabs_list")

        assert re.search(r'ID (\d+):', result).group(1) == "12"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
