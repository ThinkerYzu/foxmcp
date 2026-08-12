"""
Moving tabs, against real Firefox

Covers the scenario tabs_move was added for: collect the tabs for one site into a
window of their own. That is three tools in sequence — create_window, tabs_list to
find the tabs and read their window, tabs_move to gather them — so the value of
testing it here rather than with a stub is that the real browser assigns the window
IDs and indexes.

Reordering within a single window is tested here too, since the index arithmetic is
the browser's and not ours.
"""

import re

import pytest

import test_imports  # Automatic path setup
from mcp_client_harness import DirectMCPTestClient


SHOP_URLS = [
    "https://example.org/shop/cart",
    "https://example.org/shop/orders",
]


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


def location_of(listing, tab_id):
    """Return (window_id, index) for one tab in a tabs_list listing"""
    for line in listing.split("\n"):
        if re.search(rf'ID {tab_id}:', line):
            match = re.search(r'\[window (\d+), index (\d+)\]', line)
            assert match, f"Listing line should carry a location: {line}"
            return int(match.group(1)), int(match.group(2))
    raise AssertionError(f"Tab {tab_id} not found in listing:\n{listing}")


class TestGatherTabsIntoAWindow:
    """The scenario from issue #2: a new window, with chosen tabs moved into it"""

    @pytest.mark.asyncio
    async def test_move_tabs_to_a_new_window(self, server_with_extension):
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        created_window_id = None
        try:
            for url in SHOP_URLS:
                await call(client, "tabs_create", {"url": url, "active": False})

            listing = await call(client, "tabs_list")
            shop_tab_ids = tab_ids_for(listing, "/shop/")
            assert len(shop_tab_ids) == len(SHOP_URLS), \
                f"Both shop tabs should be listed, got {shop_tab_ids} from:\n{listing}"

            origin_window_id, _ = location_of(listing, shop_tab_ids[0])

            window_content = await call(client, "create_window", {"url": "about:blank"})
            id_match = re.search(r'ID (\d+)', window_content)
            assert id_match, f"Could not read the new window's ID from: {window_content}"
            created_window_id = int(id_match.group(1))
            assert created_window_id != origin_window_id, \
                "The new window must be a different window for this test to mean anything"

            move_content = await call(client, "tabs_move", {
                "tab_ids": shop_tab_ids,
                "window_id": created_window_id,
            })
            assert f"Moved {len(shop_tab_ids)} of {len(shop_tab_ids)}" in move_content, \
                f"Every shop tab should have moved: {move_content}"

            # The scoped listing is the check that matters: the tabs are in the new
            # window, and asking for one window really does exclude the others.
            scoped = await call(client, "tabs_list", {"window_id": created_window_id})
            for tab_id in shop_tab_ids:
                window_id, _ = location_of(scoped, tab_id)
                assert window_id == created_window_id, \
                    f"Tab {tab_id} should be in window {created_window_id}, listing says {window_id}"

            assert f"in window {created_window_id}" in scoped

            origin_listing = await call(client, "tabs_list", {"window_id": origin_window_id})
            for tab_id in shop_tab_ids:
                assert not re.search(rf'ID {tab_id}:', origin_listing), \
                    f"Tab {tab_id} should have left window {origin_window_id}:\n{origin_listing}"

        finally:
            if created_window_id is not None:
                await client.call_tool("close_window", {"window_id": created_window_id})

    @pytest.mark.asyncio
    async def test_unscoped_listing_spans_windows(self, server_with_extension):
        """tabs_list with no window_id must see tabs the current window does not hold"""
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        created_window_id = None
        try:
            first_listing = await call(client, "tabs_list")
            existing_tab_ids = tab_ids_for(first_listing, "")
            starting_window_id = (
                location_of(first_listing, existing_tab_ids[0])[0] if existing_tab_ids else None
            )

            window_content = await call(client, "create_window", {
                "url": "https://example.org/other-window",
            })
            id_match = re.search(r'ID (\d+)', window_content)
            assert id_match, f"Could not read the new window's ID from: {window_content}"
            created_window_id = int(id_match.group(1))

            listing = await call(client, "tabs_list")
            windows_seen = {
                int(m.group(1)) for m in re.finditer(r'\[window (\d+), index \d+\]', listing)
            }

            assert created_window_id in windows_seen, \
                f"The new window's tab should be listed, saw windows {windows_seen}"
            if starting_window_id is not None:
                assert starting_window_id in windows_seen, \
                    f"The original window should still be listed, saw windows {windows_seen}"
                assert len(windows_seen) > 1, \
                    f"An unscoped listing should span windows, saw only {windows_seen}"

        finally:
            if created_window_id is not None:
                await client.call_tool("close_window", {"window_id": created_window_id})


class TestReorderWithinAWindow:
    """Moving a tab without naming a window changes its position where it is"""

    @pytest.mark.asyncio
    async def test_move_tab_to_the_front(self, server_with_extension):
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        await call(client, "tabs_create", {"url": "https://example.org/last", "active": False})

        listing = await call(client, "tabs_list")
        target_ids = tab_ids_for(listing, "/last")
        assert target_ids, f"The created tab should be listed:\n{listing}"
        target_id = target_ids[0]
        window_id, starting_index = location_of(listing, target_id)

        pinned_ahead = any(
            "(pinned)" in line for line in listing.split("\n")
            if f"[window {window_id}," in line
        )
        if pinned_ahead:
            pytest.skip("A pinned tab holds index 0, which Firefox will not move past")

        move_content = await call(client, "tabs_move", {"tab_ids": target_id, "index": 0})
        assert "Moved 1 of 1" in move_content, f"The tab should have moved: {move_content}"
        assert f"ID {target_id} -> window {window_id}, index 0" in move_content

        after = await call(client, "tabs_list", {"window_id": window_id})
        _, new_index = location_of(after, target_id)
        assert new_index == 0, \
            f"Tab should sit at index 0 (was {starting_index}), listing says {new_index}"

    @pytest.mark.asyncio
    async def test_moving_an_unknown_tab_reports_an_error(self, server_with_extension):
        """A bad tab ID must come back as an error, not as a silent success"""
        setup = server_with_extension
        client = DirectMCPTestClient(setup['server'].mcp_tools)
        await client.connect()

        result = await client.call_tool("tabs_move", {"tab_ids": 999999})
        content = result.get("content", "")

        assert "Failed to move tabs" in content or "Error moving tabs" in content, \
            f"Moving a nonexistent tab should report a failure, got: {content}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
