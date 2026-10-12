"""
Native tab groups, against real Firefox

Checks what Firefox does with these calls rather than what the handlers assume:
that tabGroups.update hands back a group object, that tabGroups.query hands back
the {id, title, color, collapsed, windowId} records the handlers read, and that
grouping leaves the active tab and the focused window alone.
"""

import re

import pytest

import test_imports  # Automatic path setup
from mcp_client_harness import DirectMCPTestClient


async def call(client, name, args=None):
    """Call an MCP tool, failing the test if the call itself did not succeed"""
    result = await client.call_tool(name, args or {})
    assert result.get("success", False), f"{name} should succeed: {result}"
    return result.get("content", "")


def tab_ids_for(listing, url_fragment):
    """Return the tab IDs in a tabs_list listing whose line contains url_fragment"""
    ids = []
    for line in listing.split("\n"):
        if url_fragment in line:
            match = re.search(r'ID (\d+):', line)
            if match:
                ids.append(int(match.group(1)))
    return ids


def active_tab_id(listing):
    """Return the ID of the tab marked (active) in a tabs_list listing, or None"""
    for line in listing.split("\n"):
        if "(active)" in line:
            match = re.search(r'ID (\d+):', line)
            if match:
                return int(match.group(1))
    return None


def focused_window_id(listing):
    """Return the ID of the window marked (focused) in a list_windows listing, or None"""
    for line in listing.split("\n"):
        if "(focused)" in line:
            match = re.search(r'ID (\d+):', line)
            if match:
                return int(match.group(1))
    return None


def group_line(listing, group_id):
    """Return the tabs_groups_query line for one group ID, or None if absent"""
    for line in listing.split("\n"):
        if re.search(rf'ID {group_id}:', line):
            return line
    return None


class TestGroupCreationAndQuery:
    """tabs_group creates a group; tabs_groups_query is the only way to find its ID again"""

    @pytest.mark.asyncio
    async def test_group_id_round_trips_through_query(self, server_with_extension):
        """The ID tabs_group returns must be the same ID tabs_groups_query lists.

        tabs_group reports an ID only when it creates the group, so
        tabs_groups_query is the only way to find it again.
        """
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        created_tab_ids = []
        group_id = None
        try:
            for _ in range(2):
                content = await call(client, "tabs_create", {
                    "url": "https://example.org/groups/round-trip", "active": False,
                })
                match = re.search(r'ID (\d+)', content)
                assert match, f"tabs_create should report the new tab's ID: {content}"
                created_tab_ids.append(int(match.group(1)))

            group_content = await call(client, "tabs_group", {"tab_ids": created_tab_ids})
            id_match = re.search(r'group (\d+)', group_content)
            assert id_match, f"tabs_group should report the new group's ID: {group_content}"
            group_id = int(id_match.group(1))

            query_content = await call(client, "tabs_groups_query")
            line = group_line(query_content, group_id)
            assert line is not None, (
                f"Group {group_id} returned by tabs_group should be listed by "
                f"tabs_groups_query, got:\n{query_content}"
            )
        finally:
            if group_id is not None:
                await client.call_tool("tabs_ungroup", {"tab_ids": created_tab_ids})
            for tab_id in created_tab_ids:
                await client.call_tool("tabs_close", {"tab_id": tab_id})

    @pytest.mark.asyncio
    async def test_title_and_colour_set_at_creation_appear_in_query(self, server_with_extension):
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        created_tab_ids = []
        group_id = None
        try:
            content = await call(client, "tabs_create", {
                "url": "https://example.org/groups/styled", "active": False,
            })
            match = re.search(r'ID (\d+)', content)
            assert match, f"tabs_create should report the new tab's ID: {content}"
            created_tab_ids.append(int(match.group(1)))

            group_content = await call(client, "tabs_group", {
                "tab_ids": created_tab_ids, "title": "Research", "color": "blue",
            })
            id_match = re.search(r'group (\d+)', group_content)
            assert id_match, f"tabs_group should report the new group's ID: {group_content}"
            group_id = int(id_match.group(1))

            query_content = await call(client, "tabs_groups_query")
            line = group_line(query_content, group_id)
            assert line is not None, f"Group {group_id} should be listed:\n{query_content}"
            assert "Research" in line, f"Title should appear in the listing: {line}"
            assert "blue" in line, f"Colour should appear in the listing: {line}"
        finally:
            if group_id is not None:
                await client.call_tool("tabs_ungroup", {"tab_ids": created_tab_ids})
            for tab_id in created_tab_ids:
                await client.call_tool("tabs_close", {"tab_id": tab_id})


class TestUpdateRestylesWithoutRegrouping:
    """tabs_groups_update must change style/collapsed state without touching membership"""

    @pytest.mark.asyncio
    async def test_update_changes_title_colour_and_collapsed_in_place(self, server_with_extension):
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        created_tab_ids = []
        group_id = None
        try:
            for _ in range(2):
                content = await call(client, "tabs_create", {
                    "url": "https://example.org/groups/update", "active": False,
                })
                match = re.search(r'ID (\d+)', content)
                assert match, f"tabs_create should report the new tab's ID: {content}"
                created_tab_ids.append(int(match.group(1)))

            group_content = await call(client, "tabs_group", {
                "tab_ids": created_tab_ids, "title": "Before", "color": "red",
            })
            id_match = re.search(r'group (\d+)', group_content)
            assert id_match, f"tabs_group should report the new group's ID: {group_content}"
            group_id = int(id_match.group(1))

            update_content = await call(client, "tabs_groups_update", {
                "group_id": group_id, "title": "After", "color": "green", "collapsed": True,
            })
            assert f"Updated group {group_id}" in update_content, \
                f"tabs_groups_update should confirm the group it changed: {update_content}"

            query_content = await call(client, "tabs_groups_query")
            line = group_line(query_content, group_id)
            assert line is not None, (
                f"The group must still exist under the same ID after an update, "
                f"not be replaced by a new one:\n{query_content}"
            )
            assert "After" in line and "Before" not in line, \
                f"Title should have changed to 'After': {line}"
            assert "green" in line, f"Colour should have changed to green: {line}"
            assert "(collapsed)" in line, f"Group should now report collapsed: {line}"

            # Same tabs, same group: an update must not have regrouped anything.
            listing = await call(client, "tabs_list")
            for tab_id in created_tab_ids:
                found = any(
                    f"ID {tab_id}:" in ln for ln in listing.split("\n")
                )
                assert found, f"Tab {tab_id} should still exist after the group update"
        finally:
            if group_id is not None:
                await client.call_tool("tabs_ungroup", {"tab_ids": created_tab_ids})
            for tab_id in created_tab_ids:
                await client.call_tool("tabs_close", {"tab_id": tab_id})


class TestUngroupRemovesTabsAndEmptyGroupsVanish:
    """tabs_ungroup detaches tabs; Firefox itself deletes a group left with none"""

    @pytest.mark.asyncio
    async def test_ungroup_removes_tabs_and_empty_group_disappears(self, server_with_extension):
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        created_tab_ids = []
        group_id = None
        try:
            content = await call(client, "tabs_create", {
                "url": "https://example.org/groups/ungroup", "active": False,
            })
            match = re.search(r'ID (\d+)', content)
            assert match, f"tabs_create should report the new tab's ID: {content}"
            created_tab_ids.append(int(match.group(1)))

            group_content = await call(client, "tabs_group", {"tab_ids": created_tab_ids})
            id_match = re.search(r'group (\d+)', group_content)
            assert id_match, f"tabs_group should report the new group's ID: {group_content}"
            group_id = int(id_match.group(1))

            query_before = await call(client, "tabs_groups_query")
            assert group_line(query_before, group_id) is not None, \
                f"Group {group_id} should exist before ungrouping:\n{query_before}"

            ungroup_content = await call(client, "tabs_ungroup", {"tab_ids": created_tab_ids})
            assert "Ungrouped" in ungroup_content, \
                f"tabs_ungroup should confirm the removal: {ungroup_content}"

            query_after = await call(client, "tabs_groups_query")
            assert group_line(query_after, group_id) is None, (
                f"A group left with no tabs should be removed by Firefox and no "
                f"longer listed, but group {group_id} is still present:\n{query_after}"
            )
            group_id = None  # Already ungrouped; nothing left for the finally block to undo.

            # The tab itself must survive being ungrouped.
            listing = await call(client, "tabs_list")
            assert f"ID {created_tab_ids[0]}:" in listing, \
                "The ungrouped tab should still exist, only its group membership should be gone"
        finally:
            if group_id is not None:
                await client.call_tool("tabs_ungroup", {"tab_ids": created_tab_ids})
            for tab_id in created_tab_ids:
                await client.call_tool("tabs_close", {"tab_id": tab_id})


class TestAddingATabToAnExistingGroup:
    """Passing group_id to tabs_group must add to that group rather than create a new one

    The evidence here is the group ID that comes back: creating a second group
    would report a different one. Membership itself cannot be asserted directly,
    because tabs.list does not report a tab's group, so there is no way through
    these tools to ask which group a given tab is in.
    """

    @pytest.mark.asyncio
    async def test_second_tab_joins_the_existing_group(self, server_with_extension):
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        created_tab_ids = []
        group_id = None
        try:
            content = await call(client, "tabs_create", {
                "url": "https://example.org/groups/first", "active": False,
            })
            match = re.search(r'ID (\d+)', content)
            assert match, f"tabs_create should report the new tab's ID: {content}"
            created_tab_ids.append(int(match.group(1)))

            group_content = await call(client, "tabs_group", {
                "tab_ids": created_tab_ids, "title": "Growing",
            })
            id_match = re.search(r'group (\d+)', group_content)
            assert id_match, f"tabs_group should report the new group's ID: {group_content}"
            group_id = int(id_match.group(1))

            content = await call(client, "tabs_create", {
                "url": "https://example.org/groups/second", "active": False,
            })
            match = re.search(r'ID (\d+)', content)
            assert match, f"tabs_create should report the second tab's ID: {content}"
            created_tab_ids.append(int(match.group(1)))

            add_content = await call(client, "tabs_group", {
                "tab_ids": created_tab_ids[1], "group_id": group_id,
            })
            assert f"group {group_id}" in add_content, (
                f"Adding to an existing group should report the same group ID "
                f"{group_id}, got: {add_content}"
            )

            query_content = await call(client, "tabs_groups_query")
            line = group_line(query_content, group_id)
            assert line is not None, f"Group {group_id} should still be listed:\n{query_content}"
            assert "Growing" in line, \
                f"The pre-existing group's title should be untouched: {line}"

            # Both tabs must report the same window as the group, via tabs_list.
            listing = await call(client, "tabs_list")
            windows_seen = set()
            for tab_id in created_tab_ids:
                for ln in listing.split("\n"):
                    if f"ID {tab_id}:" in ln:
                        wmatch = re.search(r'\[window (\d+),', ln)
                        assert wmatch, f"Listing line should carry a window: {ln}"
                        windows_seen.add(int(wmatch.group(1)))
            assert len(windows_seen) == 1, (
                f"Both tabs should end up in the same window as the group, "
                f"saw {windows_seen}"
            )
        finally:
            if group_id is not None:
                await client.call_tool("tabs_ungroup", {"tab_ids": created_tab_ids})
            for tab_id in created_tab_ids:
                await client.call_tool("tabs_close", {"tab_id": tab_id})


class TestQueryFiltersByWindow:
    """tabs_groups_query's window_id filter must actually exclude other windows' groups"""

    @pytest.mark.asyncio
    async def test_window_filter_excludes_other_windows_groups(self, server_with_extension):
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        created_tab_ids = []
        created_window_id = None
        origin_group_id = None
        other_group_id = None
        try:
            content = await call(client, "tabs_create", {
                "url": "https://example.org/groups/origin-window", "active": False,
            })
            match = re.search(r'ID (\d+)', content)
            assert match, f"tabs_create should report the new tab's ID: {content}"
            created_tab_ids.append(int(match.group(1)))
            listing = await call(client, "tabs_list")
            origin_window_id = None
            for ln in listing.split("\n"):
                if f"ID {created_tab_ids[0]}:" in ln:
                    wmatch = re.search(r'\[window (\d+),', ln)
                    assert wmatch, f"Listing line should carry a window: {ln}"
                    origin_window_id = int(wmatch.group(1))
            assert origin_window_id is not None

            group_content = await call(client, "tabs_group", {
                "tab_ids": created_tab_ids, "title": "OriginWindowGroup",
            })
            id_match = re.search(r'group (\d+)', group_content)
            assert id_match, f"tabs_group should report the new group's ID: {group_content}"
            origin_group_id = int(id_match.group(1))

            window_content = await call(client, "create_window", {"url": "about:blank"})
            id_match = re.search(r'ID (\d+)', window_content)
            assert id_match, f"create_window should report the new window's ID: {window_content}"
            created_window_id = int(id_match.group(1))

            other_content = await call(client, "tabs_create", {
                "url": "https://example.org/groups/other-window",
                "active": False, "window_id": created_window_id,
            })
            match = re.search(r'ID (\d+)', other_content)
            assert match, f"tabs_create should report the new tab's ID: {other_content}"
            created_tab_ids.append(int(match.group(1)))

            other_group_content = await call(client, "tabs_group", {
                "tab_ids": created_tab_ids[1], "title": "OtherWindowGroup",
            })
            id_match = re.search(r'group (\d+)', other_group_content)
            assert id_match, f"tabs_group should report the new group's ID: {other_group_content}"
            other_group_id = int(id_match.group(1))

            scoped = await call(client, "tabs_groups_query", {"window_id": origin_window_id})
            assert group_line(scoped, origin_group_id) is not None, \
                f"The origin window's own group should be listed:\n{scoped}"
            assert group_line(scoped, other_group_id) is None, (
                f"Filtering by window_id={origin_window_id} must not leak the other "
                f"window's group {other_group_id}:\n{scoped}"
            )

            scoped_other = await call(client, "tabs_groups_query", {"window_id": created_window_id})
            assert group_line(scoped_other, other_group_id) is not None, \
                f"The other window's own group should be listed:\n{scoped_other}"
            assert group_line(scoped_other, origin_group_id) is None, (
                f"Filtering by window_id={created_window_id} must not leak the origin "
                f"window's group {origin_group_id}:\n{scoped_other}"
            )
        finally:
            if origin_group_id is not None:
                await client.call_tool("tabs_ungroup", {"tab_ids": [created_tab_ids[0]]})
            if other_group_id is not None and len(created_tab_ids) > 1:
                await client.call_tool("tabs_ungroup", {"tab_ids": [created_tab_ids[1]]})
            for tab_id in created_tab_ids:
                await client.call_tool("tabs_close", {"tab_id": tab_id})
            if created_window_id is not None:
                await client.call_tool("close_window", {"window_id": created_window_id})


class TestGroupingNeverActivatesOrFocuses:
    """None of these operations changes the active tab or which window has focus"""

    @pytest.mark.asyncio
    async def test_grouping_operations_leave_the_active_tab_unchanged(self, server_with_extension):
        """Grouping, restyling and ungrouping must not activate a tab"""
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        created_tab_ids = []
        group_id = None
        try:
            for _ in range(2):
                content = await call(client, "tabs_create", {
                    "url": "https://example.org/groups/no-activation", "active": False,
                })
                match = re.search(r'ID (\d+)', content)
                assert match, f"tabs_create should report the new tab's ID: {content}"
                created_tab_ids.append(int(match.group(1)))

            before_listing = await call(client, "tabs_list")
            active_before = active_tab_id(before_listing)
            assert active_before is not None, \
                f"There should be an active tab before grouping:\n{before_listing}"
            assert active_before not in created_tab_ids, (
                "The tabs created for this test were created with active=False; "
                "if one of them is active, tabs_create itself is stealing focus, "
                "which would make this test meaningless"
            )

            group_content = await call(client, "tabs_group", {
                "tab_ids": created_tab_ids, "title": "Quiet", "color": "purple",
            })
            id_match = re.search(r'group (\d+)', group_content)
            assert id_match, f"tabs_group should report the new group's ID: {group_content}"
            group_id = int(id_match.group(1))

            after_group_listing = await call(client, "tabs_list")
            assert active_tab_id(after_group_listing) == active_before, (
                f"tabs_group must not change the active tab. Before: {active_before}, "
                f"after: {active_tab_id(after_group_listing)}"
            )

            await call(client, "tabs_groups_update", {"group_id": group_id, "collapsed": True})
            after_update_listing = await call(client, "tabs_list")
            assert active_tab_id(after_update_listing) == active_before, (
                f"tabs_groups_update must not change the active tab. Before: "
                f"{active_before}, after: {active_tab_id(after_update_listing)}"
            )

            await call(client, "tabs_ungroup", {"tab_ids": created_tab_ids})
            group_id = None
            after_ungroup_listing = await call(client, "tabs_list")
            assert active_tab_id(after_ungroup_listing) == active_before, (
                f"tabs_ungroup must not change the active tab. Before: {active_before}, "
                f"after: {active_tab_id(after_ungroup_listing)}"
            )
        finally:
            if group_id is not None:
                await client.call_tool("tabs_ungroup", {"tab_ids": created_tab_ids})
            for tab_id in created_tab_ids:
                await client.call_tool("tabs_close", {"tab_id": tab_id})

    @pytest.mark.asyncio
    async def test_grouping_in_a_background_window_leaves_focus_alone(self, server_with_extension):
        """Grouping tabs in an unfocused window must not focus that window

        A new group is created in its first tab's window, so the tabs are put in a
        window opened without focus: that is where focusing would show up.
        """
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        background_window_id = None
        created_tab_ids = []
        group_id = None
        try:
            focused_before = focused_window_id(await call(client, "list_windows"))
            assert focused_before is not None, "Some window should have focus before the test"

            # Firefox focuses a new window even when asked not to, so hand focus back.
            window_content = await call(client, "create_window", {"url": "about:blank"})
            id_match = re.search(r'ID (\d+)', window_content)
            assert id_match, f"create_window should report the new window's ID: {window_content}"
            background_window_id = int(id_match.group(1))
            await call(client, "focus_window", {"window_id": focused_before})

            listing = await call(client, "list_windows")
            assert focused_window_id(listing) == focused_before, (
                f"Focus did not return to window {focused_before}, so this test "
                f"cannot tell whether grouping moves it:\n{listing}"
            )

            for _ in range(2):
                content = await call(client, "tabs_create", {
                    "url": "https://example.org/groups/background-window",
                    "active": False, "window_id": background_window_id,
                })
                match = re.search(r'ID (\d+)', content)
                assert match, f"tabs_create should report the new tab's ID: {content}"
                created_tab_ids.append(int(match.group(1)))

            group_content = await call(client, "tabs_group", {
                "tab_ids": created_tab_ids, "title": "Background", "color": "cyan",
            })
            id_match = re.search(r'group (\d+)', group_content)
            assert id_match, f"tabs_group should report the new group's ID: {group_content}"
            group_id = int(id_match.group(1))

            for step, tool, args in [
                ("tabs_group", None, None),
                ("tabs_groups_update", "tabs_groups_update", {"group_id": group_id, "collapsed": True}),
                ("tabs_ungroup", "tabs_ungroup", {"tab_ids": created_tab_ids}),
            ]:
                if tool:
                    await call(client, tool, args)
                listing = await call(client, "list_windows")
                assert focused_window_id(listing) == focused_before, (
                    f"{step} must not change which window has focus. Before: "
                    f"{focused_before}, after: {focused_window_id(listing)}\n{listing}"
                )
            group_id = None
        finally:
            if group_id is not None:
                await client.call_tool("tabs_ungroup", {"tab_ids": created_tab_ids})
            for tab_id in created_tab_ids:
                await client.call_tool("tabs_close", {"tab_id": tab_id})
            if background_window_id is not None:
                await client.call_tool("close_window", {"window_id": background_window_id})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
