"""
Tests for leaving tool groups unregistered

A tool's description sits in the client's context for the whole session whether
or not it is ever called, so a user who never touches bookmarks still pays for
them on every request. --disable-tools drops a group before registration, which
is the only way to keep it out of that context - a tool that is registered and
merely rejected at call time still costs its description.

--enable-tools names one tool to register anyway, for the case where a single
tool out of a disabled group is the one that is wanted - a screenshot without
the five other tab tools, which is what issue #6 asked for.

The tests worth having here are the ones that catch drift: that the groups
partition the tool surface, so a tool added tomorrow cannot be silently
unreachable by the option, that a tool named individually outlives its group,
and that a mistyped name is refused rather than quietly ignored.
"""

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools
from server.server import FoxMCPServer


class StubWebSocketServer:
    """Stands in for the WebSocket server; these tests never send a request"""

    async def send_request_and_wait(self, request):
        return {"type": "response", "data": {}}

    async def get_extension_status(self):
        return "No browser extension is connected"


async def tool_names(disabled_groups=None, enabled_tools=None):
    """Names of the tools registered with a given set of groups disabled

    enabled_tools names tools to keep despite their group being disabled, the
    same as the option of that name.
    """
    tools = FoxMCPTools(StubWebSocketServer(), disabled_groups=disabled_groups,
                        enabled_tools=enabled_tools)
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


class TestTheServerPassesTheOptionThrough:
    """The tests above build FoxMCPTools directly; --disable-tools does not

    What a user's command line reaches is FoxMCPServer(disabled_tool_groups=...),
    and every step between the two is untested by the rest of this file. A
    keyword that stopped being forwarded there would leave every group enabled
    with no error to show for it.
    """

    @pytest.mark.asyncio
    async def test_a_group_disabled_on_the_server_is_not_registered(self):
        """The flag's whole purpose: the group never reaches the client"""
        server = FoxMCPServer(disabled_tool_groups=['bookmarks'], start_mcp=False)

        registered = {tool.name for tool in await server.mcp_tools.mcp.list_tools()}

        assert not {name for name in registered if name.startswith('bookmarks_')}
        assert 'tabs_list' in registered

    def test_the_server_refuses_an_unknown_group(self):
        """main() turns this ValueError into argparse's usage message"""
        with pytest.raises(ValueError):
            FoxMCPServer(disabled_tool_groups=['nope'], start_mcp=False)

    @pytest.mark.asyncio
    async def test_a_tool_enabled_on_the_server_survives_its_group(self):
        """The two options have to arrive together, or the second one does nothing"""
        server = FoxMCPServer(disabled_tool_groups=['tabs'],
                              enabled_tools=['tabs_capture_screenshot'],
                              start_mcp=False)

        registered = {tool.name for tool in await server.mcp_tools.mcp.list_tools()}

        assert 'tabs_capture_screenshot' in registered
        assert 'tabs_list' not in registered

    def test_the_server_refuses_an_unknown_tool(self):
        """main() turns this one into a usage message too, by catching it around
        the constructor - the tool names do not exist until the definitions run
        """
        with pytest.raises(ValueError):
            FoxMCPServer(enabled_tools=['tabs_screenshot'], start_mcp=False)


class TestEnablingASingleTool:
    """One tool named individually outlives the group it belongs to"""

    @pytest.mark.asyncio
    async def test_the_named_tool_survives_and_the_rest_of_its_group_does_not(self):
        """Issue #6: a screenshot of the page, without the tab tools around it

        tabs_capture_screenshot takes no tab ID - it captures the visible tab -
        so it is usable on its own, which is what makes this worth doing rather
        than moving the tool to another group.
        """
        remaining = await tool_names(['tabs'], ['tabs_capture_screenshot'])

        assert 'tabs_capture_screenshot' in remaining
        assert not {name for name in remaining
                    if name.startswith('tabs_') and name != 'tabs_capture_screenshot'}

    @pytest.mark.asyncio
    async def test_tools_can_be_kept_from_more_than_one_disabled_group(self):
        """Each name is judged on its own, not against a single group"""
        remaining = await tool_names(['tabs', 'history'],
                                     ['tabs_capture_screenshot', 'history_query'])

        assert 'tabs_capture_screenshot' in remaining
        assert 'history_query' in remaining
        assert 'tabs_list' not in remaining
        assert 'history_get_recent' not in remaining

    @pytest.mark.asyncio
    async def test_enabling_a_tool_whose_group_is_on_changes_nothing(self):
        """Naming a tool that was never dropped is a no-op, not an error

        A user who disables a group later, or who copies the option between
        setups, should not have to keep the two lists in step by hand.
        """
        assert await tool_names([], ['tabs_list']) == await tool_names()

    @pytest.mark.asyncio
    async def test_an_enabled_tool_still_works(self):
        """Registration is all that was skipped, so the tool is the same tool"""
        tools = FoxMCPTools(StubWebSocketServer(), disabled_groups=['debug'],
                            enabled_tools=['debug_websocket_status'])

        result = await tools.mcp.call_tool('debug_websocket_status', {})

        assert result is not None


class TestUnknownToolNames:
    """A mistyped tool name loses the one tool the user asked to keep"""

    def test_unknown_tool_is_refused(self):
        """'tabs_screenshot' for 'tabs_capture_screenshot' would silently keep nothing"""
        with pytest.raises(ValueError) as excinfo:
            FoxMCPTools(StubWebSocketServer(), disabled_groups=['tabs'],
                        enabled_tools=['tabs_screenshot'])

        assert 'tabs_screenshot' in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_the_error_lists_the_valid_tools(self):
        """A group name is guessable from the docs; a tool name is worth spelling out"""
        with pytest.raises(ValueError) as excinfo:
            FoxMCPTools(StubWebSocketServer(), enabled_tools=['nope'])

        for name in await tool_names():
            assert name in str(excinfo.value)

    def test_one_bad_name_among_good_ones_is_still_refused(self):
        """Partial application would keep less than the user asked for"""
        with pytest.raises(ValueError):
            FoxMCPTools(StubWebSocketServer(), disabled_groups=['tabs'],
                        enabled_tools=['tabs_capture_screenshot', 'nope'])
