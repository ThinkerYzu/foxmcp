"""
Tests for moving bookmarks and for the positions bookmarks_list reports

bookmarks_move takes a destination folder, a position, or both, and the position
is only usable if bookmarks_list says where each entry sits now.

These tests stub the WebSocket server, so they check the request the tool builds
and the answer it renders, not the browser's behavior. The move itself, and the
refusal of a parent that is not a folder, are covered against real Firefox in
tests/integration/test_bookmark_management.py.
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
        self.response = {"type": "response", "data": {"bookmark": {}}}

    async def send_request_and_wait(self, request, timeout=30.0):
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
        return await tool.fn(profile_id=1, **kwargs)

    return call


class TestMoveRequest:
    """What bookmarks_move puts on the wire"""

    @pytest.mark.asyncio
    async def test_parent_only(self, call_tool, stub_server):
        """Without an index the extension gets none, and Firefox puts the item at the end"""
        await call_tool("bookmarks_move", bookmark_id="bm1", parent_id="folder1")

        assert stub_server.sent_request["action"] == "bookmarks.move"
        assert stub_server.sent_request["data"] == {"bookmarkId": "bm1", "parentId": "folder1"}

    @pytest.mark.asyncio
    async def test_index_zero_is_sent(self, call_tool, stub_server):
        """0 is the first place; a truthiness test would drop it and move the item to the end"""
        await call_tool("bookmarks_move", bookmark_id="bm1", index=0)

        assert stub_server.sent_request["data"] == {"bookmarkId": "bm1", "index": 0}

    @pytest.mark.asyncio
    async def test_parent_and_index(self, call_tool, stub_server):
        await call_tool("bookmarks_move", bookmark_id="bm1", parent_id="folder1", index=2)

        assert stub_server.sent_request["data"] == {
            "bookmarkId": "bm1", "parentId": "folder1", "index": 2}


class TestMoveRefusals:
    """Calls the tool turns away without asking the extension"""

    @pytest.mark.asyncio
    async def test_neither_parent_nor_index(self, call_tool, stub_server):
        """Firefox would move the item to the end of its folder, which nobody asked for"""
        result = await call_tool("bookmarks_move", bookmark_id="bm1")

        assert result.startswith("Error:")
        assert "parent_id or index" in result
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_negative_index(self, call_tool, stub_server):
        result = await call_tool("bookmarks_move", bookmark_id="bm1", index=-1)

        assert result.startswith("Error:")
        assert stub_server.sent_request is None


class TestMoveReply:
    """What bookmarks_move tells the caller"""

    @pytest.mark.asyncio
    async def test_reports_where_firefox_put_it(self, call_tool, stub_server):
        """The index comes from Firefox's reply, which reflects clamping past the end"""
        stub_server.response = {"type": "response", "data": {"bookmark": {
            "id": "bm1", "title": "Searchfox", "parentId": "folder1", "index": 3}}}

        result = await call_tool("bookmarks_move", bookmark_id="bm1", parent_id="folder1", index=99)

        assert result == "Moved Searchfox (ID: bm1) to folder folder1 at index 3"

    @pytest.mark.asyncio
    async def test_extension_error_is_passed_on(self, call_tool, stub_server):
        stub_server.response = {"type": "error", "data": {
            "code": "INVALID_PARAMETER", "message": "Parent bm2 is a bookmark, not a folder"}}

        result = await call_tool("bookmarks_move", bookmark_id="bm1", parent_id="bm2")

        assert result == "Failed to move bookmark: Parent bm2 is a bookmark, not a folder"


class TestListShowsIndex:
    """bookmarks_list reports each entry's position, which bookmarks_move's index needs"""

    @pytest.mark.asyncio
    async def test_each_line_has_its_index(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"bookmarks": [
            {"id": "folder1", "title": "Work", "isFolder": True,
             "parentId": "toolbar_____", "index": 1},
            {"id": "bm1", "title": "Searchfox", "url": "https://example.org/",
             "isFolder": False, "parentId": "folder1", "index": 0},
        ]}}

        result = await call_tool("bookmarks_list", folder_id="folder1")

        assert "(ID: folder1, Parent: toolbar_____, Index: 1)" in result
        assert "(ID: bm1, Parent: folder1, Index: 0)" in result

    @pytest.mark.asyncio
    async def test_root_has_no_index(self, call_tool, stub_server):
        """The root has neither parent nor index, so its line says nothing about either"""
        stub_server.response = {"type": "response", "data": {"bookmarks": [
            {"id": "root________", "title": "", "isFolder": True},
        ]}}

        result = await call_tool("bookmarks_list")

        assert "Index" not in result
