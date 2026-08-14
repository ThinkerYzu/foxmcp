"""
Tests for leaving tool groups unregistered

A tool's description sits in the client's context for the whole session whether
or not it is ever called, so a user who never touches bookmarks still pays for
them on every request. --disable-tools drops a group before registration, which
is the only way to keep it out of that context - a tool that is registered and
merely rejected at call time still costs its description.

The tests worth having here are the ones that catch drift: that the groups
partition the tool surface, so a tool added tomorrow cannot be silently
unreachable by the option, and that a mistyped group name is refused rather
than quietly ignored.
"""

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Stands in for the WebSocket server; these tests never send a request"""

    async def send_request_and_wait(self, request):
        return {"type": "response", "data": {}}


async def tool_names(disabled_groups=None):
    """Names of the tools registered with a given set of groups disabled"""
    tools = FoxMCPTools(StubWebSocketServer(), disabled_groups=disabled_groups)
    return {tool.name for tool in await tools.mcp.list_tools()}


class TestGroupsCoverEveryTool:
    """The groups have to partition the surface, or the option has blind spots"""

    @pytest.mark.asyncio
    async def test_every_tool_belongs_to_some_group(self):
        """A tool in no group could never be disabled, and nothing would say so

        This is the test that catches a new tool registered from a method
        TOOL_GROUPS does not name.
        """
        all_tools = await tool_names()
        covered = set()
        for group in FoxMCPTools.TOOL_GROUPS:
            covered |= all_tools - await tool_names([group])

        assert covered == all_tools, f"tools in no group: {sorted(all_tools - covered)}"

    @pytest.mark.asyncio
    async def test_no_tool_belongs_to_two_groups(self):
        """Disabling every group must leave nothing behind, and drop each tool once"""
        all_tools = await tool_names()
        removed_count = 0
        for group in FoxMCPTools.TOOL_GROUPS:
            removed_count += len(all_tools - await tool_names([group]))

        assert await tool_names(list(FoxMCPTools.TOOL_GROUPS)) == set()
        assert removed_count == len(all_tools)

    @pytest.mark.asyncio
    async def test_disabling_nothing_registers_everything(self):
        """The default is unchanged - every group is on unless a user turns it off"""
        assert await tool_names() == await tool_names([])


class TestDisablingGroups:
    """What a disabled group takes with it, and what it leaves alone"""

    @pytest.mark.asyncio
    async def test_bookmarks_group_drops_exactly_its_own_tools(self):
        """The group named in issue #4, checked tool by tool rather than by count"""
        remaining = await tool_names(['bookmarks'])

        assert not {name for name in remaining if name.startswith('bookmarks_')}
        assert 'tabs_list' in remaining

    @pytest.mark.asyncio
    async def test_several_groups_can_be_disabled_at_once(self):
        """Groups are independent - disabling two drops the union of their tools"""
        remaining = await tool_names(['bookmarks', 'history'])

        assert 'bookmarks_list' not in remaining
        assert 'history_query' not in remaining
        assert 'tabs_list' in remaining

    @pytest.mark.asyncio
    async def test_debug_survives_disabling_history(self):
        """debug_websocket_status used to be registered by the history group

        It is the tool you reach for when the connection looks wrong, so having it
        vanish with an unrelated group would be a bad surprise.
        """
        assert 'debug_websocket_status' in await tool_names(['history'])
        assert 'debug_websocket_status' not in await tool_names(['debug'])


class TestUnknownGroupNames:
    """A typo has to fail loudly, since the symptom otherwise is silence"""

    def test_unknown_group_is_refused(self):
        """'bookmark' for 'bookmarks' would otherwise register everything as normal"""
        with pytest.raises(ValueError) as excinfo:
            FoxMCPTools(StubWebSocketServer(), disabled_groups=['bookmark'])

        assert 'bookmark' in str(excinfo.value)

    def test_the_error_lists_the_valid_groups(self):
        """The caller is a person at a command line, and the list is short"""
        with pytest.raises(ValueError) as excinfo:
            FoxMCPTools(StubWebSocketServer(), disabled_groups=['nope'])

        for group in FoxMCPTools.TOOL_GROUPS:
            assert group in str(excinfo.value)

    def test_one_bad_name_among_good_ones_is_still_refused(self):
        """Partial application would disable less than the user asked for"""
        with pytest.raises(ValueError):
            FoxMCPTools(StubWebSocketServer(), disabled_groups=['bookmarks', 'nope'])
