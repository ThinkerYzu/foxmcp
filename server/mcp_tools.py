#!/usr/bin/env python3
"""
MCP Tool definitions for FoxMCP server
These tools bridge browser functions through WebSocket to the Firefox extension

Copyright (c) 2024 FoxMCP Project
Licensed under the MIT License - see LICENSE file for details
"""

import asyncio
import logging
import uuid
import os
import subprocess
import time
import json
import base64
from datetime import datetime
from typing import Dict, Any, Optional, List, TypedDict, Union

from fastmcp import FastMCP
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Longest a single script argument may appear in the log before being cut short.
#
# Arguments carry real content - a Bugzilla comment, a chat message - so the log
# records them: knowing that element-send-message.sh ran without knowing what it
# sent is not an audit trail. The cap keeps one long comment from burying the
# rest of the log, since start.sh writes it to a plain file that only truncates
# when the server restarts.
MAX_LOGGED_ARG_LENGTH = 120


def format_script_args_for_log(args_list):
    """Render predefined-script arguments as a single line for the log

    Long arguments are cut to MAX_LOGGED_ARG_LENGTH with an ellipsis and their
    full length appended, so a truncated entry still says how much was elided.
    Returns "(no arguments)" for an empty list rather than an empty string,
    which would read as missing information in the log.
    """
    if not args_list:
        return "(no arguments)"

    rendered = []
    for arg in args_list:
        if len(arg) > MAX_LOGGED_ARG_LENGTH:
            rendered.append(f"{arg[:MAX_LOGGED_ARG_LENGTH]!r}...[{len(arg)} chars]")
        else:
            rendered.append(repr(arg))
    return ", ".join(rendered)

class TabInfo(TypedDict):
    """Type definition for tab information from browser extension"""
    url: str
    id: int
    title: str
    active: bool
    windowId: int
    pinned: bool
    index: int

class TabsListResponse(TypedDict):
    """Type definition for tabs.list response from browser extension"""
    tabs: List[TabInfo]
    debug: Dict[str, Any]

class FoxMCPTools:
    """MCP tools that communicate with Firefox extension via WebSocket"""

    def __init__(self, websocket_server):
        """Initialize with reference to WebSocket server"""
        self.websocket_server = websocket_server
        self.mcp = FastMCP("FoxMCP")
        self._setup_tools()

    def _setup_tools(self):
        """Set up all MCP tool definitions"""
        self._setup_window_tools()
        self._setup_tab_tools()
        self._setup_history_tools()
        self._setup_bookmark_tools()
        self._setup_navigation_tools()
        self._setup_content_tools()
        self._setup_request_monitoring_tools()

    def _setup_window_tools(self):
        """Setup window management tools"""

        @self.mcp.tool()
        async def list_windows(populate: bool = True) -> str:
            """
            List all browser windows
            
            Args:
                populate: Whether to include tab information for each window
                
            Returns:
                String containing list of windows with their details
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.list",
                "data": {"populate": populate},
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error getting windows: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                windows_data = response["data"]
                windows = windows_data.get("windows", [])
                if not windows:
                    return "No windows found"

                result = f"Browser windows ({len(windows)} found):\n"
                for window in windows:
                    state_info = f"state: {window.get('state', 'unknown')}"
                    focused_info = " (focused)" if window.get("focused") else ""
                    size_info = f"{window.get('width', '?')}x{window.get('height', '?')}"
                    tabs_count = len(window.get('tabs', [])) if populate else '?'
                    result += f"- ID {window.get('id')}: {window.get('type', 'normal')} window, {state_info}, {size_info}, {tabs_count} tabs{focused_info}\n"
                return result

            return "Unable to retrieve windows"

        @self.mcp.tool()
        async def get_window(window_id: int, populate: bool = True) -> str:
            """
            Get information about a specific window
            
            Args:
                window_id: The ID of the window to retrieve
                populate: Whether to include tab information
                
            Returns:
                String containing window details
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.get",
                "data": {"windowId": window_id, "populate": populate},
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error getting window {window_id}: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                window_data = response["data"].get("window", {})
                if not window_data:
                    return f"Window {window_id} not found"

                state_info = f"state: {window_data.get('state', 'unknown')}"
                focused_info = " (focused)" if window_data.get("focused") else ""
                size_info = f"{window_data.get('width', '?')}x{window_data.get('height', '?')}"
                tabs_count = len(window_data.get('tabs', [])) if populate else '?'
                return f"Window {window_data.get('id')}: {window_data.get('type', 'normal')} window, {state_info}, {size_info}, {tabs_count} tabs{focused_info}"

            return f"Unable to retrieve window {window_id}"

        @self.mcp.tool()
        async def get_current_window(populate: bool = True) -> str:
            """
            Get the current active window
            
            Args:
                populate: Whether to include tab information
                
            Returns:
                String containing current window details
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.get_current",
                "data": {"populate": populate},
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error getting current window: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                window_data = response["data"].get("window", {})
                if not window_data:
                    return "No current window found"

                state_info = f"state: {window_data.get('state', 'unknown')}"
                size_info = f"{window_data.get('width', '?')}x{window_data.get('height', '?')}"
                tabs_count = len(window_data.get('tabs', [])) if populate else '?'
                return f"Current window (ID {window_data.get('id')}): {window_data.get('type', 'normal')} window, {state_info}, {size_info}, {tabs_count} tabs"

            return "Unable to retrieve current window"

        @self.mcp.tool()
        async def get_last_focused_window(populate: bool = True) -> str:
            """
            Get the last focused window
            
            Args:
                populate: Whether to include tab information
                
            Returns:
                String containing last focused window details
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.get_last_focused",
                "data": {"populate": populate},
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error getting last focused window: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                window_data = response["data"].get("window", {})
                if not window_data:
                    return "No last focused window found"

                state_info = f"state: {window_data.get('state', 'unknown')}"
                size_info = f"{window_data.get('width', '?')}x{window_data.get('height', '?')}"
                tabs_count = len(window_data.get('tabs', [])) if populate else '?'
                return f"Last focused window (ID {window_data.get('id')}): {window_data.get('type', 'normal')} window, {state_info}, {size_info}, {tabs_count} tabs"

            return "Unable to retrieve last focused window"

        @self.mcp.tool()
        async def create_window(
            url: Optional[str] = None,
            window_type: str = "normal",
            state: str = "normal", 
            focused: bool = True,
            width: Optional[int] = None,
            height: Optional[int] = None,
            top: Optional[int] = None,
            left: Optional[int] = None,
            incognito: bool = False
        ) -> str:
            """
            Create a new browser window
            
            Args:
                url: URL to load in the new window
                window_type: Type of window ("normal", "popup", "panel", "detached_panel")
                state: Window state ("normal", "minimized", "maximized", "fullscreen")
                focused: Whether to focus the new window
                width: Window width in pixels
                height: Window height in pixels  
                top: Window top position in pixels
                left: Window left position in pixels
                incognito: Whether to create an incognito window
                
            Returns:
                String containing created window details
            """
            data = {'type': window_type, 'state': state, 'focused': focused, 'incognito': incognito}
            if url: data['url'] = url
            if width: data['width'] = width
            if height: data['height'] = height
            if top is not None: data['top'] = top
            if left is not None: data['left'] = left
            
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.create",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error creating window: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                window_data = response["data"].get("window", {})
                if window_data:
                    window_id = window_data.get('id')
                    window_url = url or "about:blank"
                    size_info = f"{window_data.get('width', '?')}x{window_data.get('height', '?')}"
                    return f"Created {window_type} window (ID {window_id}): {window_url}, {size_info}"

            return "Window created but unable to retrieve details"

        @self.mcp.tool() 
        async def close_window(window_id: int) -> str:
            """
            Close a browser window
            
            Args:
                window_id: The ID of the window to close
                
            Returns:
                String indicating success/failure
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.close",
                "data": {"windowId": window_id},
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error closing window {window_id}: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                if response["data"].get("success"):
                    return f"Window {window_id} closed successfully"
                else:
                    return f"Failed to close window {window_id}"

            return f"Unable to close window {window_id}"

        @self.mcp.tool()
        async def focus_window(window_id: int) -> str:
            """
            Bring a window to front and focus it
            
            Args:
                window_id: The ID of the window to focus
                
            Returns:
                String indicating success/failure
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.focus",
                "data": {"windowId": window_id},
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error focusing window {window_id}: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                if response["data"].get("success"):
                    return f"Window {window_id} focused successfully"
                else:
                    return f"Failed to focus window {window_id}"

            return f"Unable to focus window {window_id}"

        @self.mcp.tool()
        async def update_window(
            window_id: int,
            state: Optional[str] = None,
            focused: Optional[bool] = None,
            width: Optional[int] = None,
            height: Optional[int] = None,
            top: Optional[int] = None,
            left: Optional[int] = None
        ) -> str:
            """
            Update window properties
            
            Args:
                window_id: The ID of the window to update
                state: New window state ("normal", "minimized", "maximized", "fullscreen")
                focused: Whether to focus the window
                width: New window width in pixels
                height: New window height in pixels
                top: New window top position in pixels
                left: New window left position in pixels
                
            Returns:
                String containing updated window details
            """
            data = {'windowId': window_id}
            if state: data['state'] = state
            if focused is not None: data['focused'] = focused
            if width: data['width'] = width
            if height: data['height'] = height
            if top is not None: data['top'] = top
            if left is not None: data['left'] = left
            
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.update",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error updating window {window_id}: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                window_data = response["data"].get("window", {})
                if window_data:
                    state_info = f"state: {window_data.get('state', 'unknown')}"
                    size_info = f"{window_data.get('width', '?')}x{window_data.get('height', '?')}"
                    return f"Updated window {window_id}: {state_info}, {size_info}"
                else:
                    return f"Window {window_id} updated successfully"

            return f"Unable to update window {window_id}"

    def _setup_tab_tools(self):
        """Setup tab management tools"""

        # Tab List Tool
        @self.mcp.tool()
        async def tabs_list(window_id: Optional[Union[int, str]] = None) -> str:
            """
            List open browser tabs, across every window or within one window

            Each line ends with "[window {id}, index {n}]", and carries "(active)" for the
            active tab of its window and "(pinned)" for a pinned one. The window, the index
            and the pinned mark are what tabs_move needs: the window to move a tab out of or
            into, the position it currently holds, and whether a leading run of pinned tabs
            blocks the low indexes.

            Args:
                window_id: Restrict the listing to this window (optional, accepts int or
                    string). Omit it to list tabs in every window.

            Returns:
                Formatted string with tab information:
                "Open tabs ({count} found):
                - ID {tab_id}: {title} - {url}{status_indicators} [window {window_id}, index {index}]"

                The index is the tab's position in its window, counting from 0 — pass it to
                tabs_move to reorder.

                Not exposed to clients — see the description above.
            """
            # Convert window_id to int if it's a string (for MCP client compatibility)
            if window_id is not None and isinstance(window_id, str):
                try:
                    window_id = int(window_id)
                except (ValueError, TypeError):
                    return f"Error: Invalid window_id '{window_id}'. Must be a valid integer."

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.list",
                "data": {
                    **({"windowId": window_id} if window_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error getting tabs: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                tabs_data: TabsListResponse = response["data"]
                tabs: List[TabInfo] = tabs_data.get("tabs", [])
                if not tabs:
                    # More informative message for debugging
                    return f"No tabs found. Extension response: {response.get('data', {})}"

                # The location goes at the end of the line, not next to the tab ID.
                #
                # Callers pick tab IDs out of this listing with an `ID (\d+):` pattern, so
                # nothing may come between the ID and its colon. One test in the suite feeds
                # that match into pytest.skip, which would quietly stop testing rather than
                # fail if the pattern broke.
                scope = f" in window {window_id}" if window_id else ""
                result = f"Open tabs{scope} ({len(tabs)} found):\n"
                for tab in tabs:
                    active = " (active)" if tab.get("active") else ""
                    pinned = " (pinned)" if tab.get("pinned") else ""
                    location = f" [window {tab.get('windowId')}, index {tab.get('index')}]"
                    result += f"- ID {tab.get('id')}: {tab.get('title', 'No title')} - {tab.get('url', 'No URL')}{active}{pinned}{location}\n"
                return result

            return "Unable to retrieve tabs"

        # Tab Create Tool
        @self.mcp.tool()
        async def tabs_create(
            url: str,
            active: bool = True,
            pinned: bool = False,
            window_id: Optional[Union[int, str]] = None
        ) -> str:
            """Create a new browser tab

            Args:
                url: URL to open in the new tab
                active: Whether the tab should be active (default: True)
                pinned: Whether the tab should be pinned (default: False)
                window_id: Window ID to create tab in (optional, accepts int or string)
            """
            # Convert window_id to int if it's a string (for MCP client compatibility)
            if window_id is not None and isinstance(window_id, str):
                try:
                    window_id = int(window_id)
                except (ValueError, TypeError):
                    return f"Error: Invalid window_id '{window_id}'. Must be a valid integer."
            
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.create",
                "data": {
                    "url": url,
                    "active": active,
                    "pinned": pinned,
                    **({"windowId": window_id} if window_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error creating tab: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                tab = response["data"].get("tab", {})
                return f"Created tab: ID {tab.get('id')} - {tab.get('title', 'Loading...')} - {tab.get('url', url)}"

            return "Unable to create tab"

        # Tab Close Tool
        @self.mcp.tool()
        async def tabs_close(tab_id: int) -> str:
            """Close a browser tab

            Args:
                tab_id: ID of the tab to close
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.close",
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error closing tab: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully closed tab {tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to close tab: {error_msg}"

            return f"Unable to close tab {tab_id}"

        # Tab Switch Tool
        @self.mcp.tool()
        async def tabs_switch(tab_id: int) -> str:
            """Switch to a specific browser tab

            Args:
                tab_id: ID of the tab to switch to
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.switch",
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error switching to tab: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully switched to tab {tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to switch to tab: {error_msg}"

            return f"Unable to switch to tab {tab_id}"

        # Tab Move Tool
        @self.mcp.tool()
        async def tabs_move(
            tab_ids: Union[int, str, List[Union[int, str]]],
            window_id: Optional[Union[int, str]] = None,
            index: int = -1
        ) -> str:
            """Move tabs to a new position, optionally into another window

            Reorders tabs within their window, or gathers them into a different window —
            to collect every tab for one site into a window of its own, create the window
            with create_window and pass its ID here.

            Succeeding partially is normal, so check the result: it reads
            "Moved {n} of {m}", and a tab missing from the list did not move. Firefox
            declines some moves without raising an error, and the common one is that
            **an unpinned tab cannot be placed in front of a pinned tab** — with 3 pinned
            tabs, the lowest index an unpinned tab can reach is 3, and asking for 0, 1 or 2
            moves nothing. Use tabs_list to see which tabs are pinned and what index each
            tab currently holds. A pinned tab can be moved to index 0 freely.

            Moving between windows requires both to be normal windows, not popups, and
            either both private or both non-private.

            Args:
                tab_ids: Tab ID, or several as a list (`[12, 15]`) or a JSON string
                    (`"[12, 15]"`). Listed tabs keep their given order at the destination.
                window_id: Window to move the tabs into (optional, accepts int or string).
                    Omit it to reorder within each tab's current window.
                index: Position to move to, counting from 0; -1 means the end (default: -1).
                    An index inside a leading run of pinned tabs is refused for an unpinned
                    tab — the move reports "No tabs moved" rather than failing.

            Returns:
                "Moved {n} of {m} tab(s):" and one line per moved tab with its new window
                and index, or "No tabs moved." when Firefox declined every one. Note that
                FastMCP does not expose this section to clients — anything a caller must
                know belongs in the description above or on the arguments.
            """
            # A JSON string is how MCP clients that cannot send arrays pass a list, the same
            # convention content_execute_predefined uses for its arguments.
            if isinstance(tab_ids, str):
                try:
                    tab_ids = json.loads(tab_ids)
                except json.JSONDecodeError:
                    return f"Error: Invalid tab_ids '{tab_ids}'. Must be an integer or a JSON list of integers."

            requested_ids = tab_ids if isinstance(tab_ids, list) else [tab_ids]
            if not requested_ids:
                return "Error: tab_ids is empty. Provide at least one tab ID."

            normalized_ids: List[int] = []
            for tab_id in requested_ids:
                try:
                    normalized_ids.append(int(tab_id))
                except (ValueError, TypeError):
                    return f"Error: Invalid tab ID '{tab_id}'. Must be a valid integer."

            # Convert window_id to int if it's a string (for MCP client compatibility)
            if window_id is not None and isinstance(window_id, str):
                try:
                    window_id = int(window_id)
                except (ValueError, TypeError):
                    return f"Error: Invalid window_id '{window_id}'. Must be a valid integer."

            if index < -1:
                return f"Error: Invalid index {index}. Must be -1 (end) or 0 or greater."

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.move",
                "data": {
                    "tabIds": normalized_ids,
                    "index": index,
                    **({"windowId": window_id} if window_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error moving tabs: {response['error']}"

            if response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to move tabs: {error_msg}"

            if response.get("type") == "response" and "data" in response:
                moved_tabs: List[TabInfo] = response["data"].get("tabs", [])
                if not moved_tabs:
                    return (
                        f"No tabs moved. Firefox refused the move of {len(normalized_ids)} tab(s) — "
                        "check that the target index is not in front of a pinned tab."
                    )

                result = f"Moved {len(moved_tabs)} of {len(normalized_ids)} tab(s):\n"
                for tab in moved_tabs:
                    result += f"- ID {tab.get('id')} -> window {tab.get('windowId')}, index {tab.get('index')}: {tab.get('title', 'No title')}\n"
                return result

            return "Unable to move tabs"

        # Tab Screenshot Tool
        @self.mcp.tool()
        async def tabs_capture_screenshot(
            filename: Optional[str] = None,
            window_id: Optional[int] = None,
            format: str = "png",
            quality: int = 90
        ) -> str:
            """Capture a screenshot of the visible tab

            What comes back depends on whether you pass a filename: with one, the image is
            written to disk and you get a success message and the path; without one, you get
            the image inline as a base64 data URL, which for a full window is large.

            Args:
                filename: Name of the file to save the screenshot (optional, if not provided returns base64)
                window_id: ID of the window to capture (optional, defaults to current window)
                format: Image format ('png' or 'jpeg', default: 'png')
                quality: Image quality for JPEG format (1-100, default: 90)

            Returns:
                Success message with file path if filename provided, otherwise base64 encoded image data URL

                Not exposed to clients — see the description above.
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.captureVisibleTab",
                "data": {
                    **({"windowId": window_id} if window_id else {}),
                    "format": format,
                    "quality": quality
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error capturing screenshot: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                data_url = response["data"].get("dataUrl", "")
                captured_format = response["data"].get("format", format)
                captured_quality = response["data"].get("quality", quality)
                captured_window_id = response["data"].get("windowId", "current")

                if not data_url:
                    return "No screenshot data received"

                # Extract the base64 part from data URL
                data_prefix = f"data:image/{captured_format};base64,"
                if not data_url.startswith(data_prefix):
                    return f"Screenshot captured but unexpected format: {data_url[:100]}..."

                base64_data = data_url[len(data_prefix):]

                # If filename is provided, save to file
                if filename:
                    try:
                        # Add file extension if not provided
                        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                            filename = f"{filename}.{captured_format}"

                        # Decode base64 and save to file
                        image_data = base64.b64decode(base64_data)
                        with open(filename, 'wb') as f:
                            f.write(image_data)

                        file_size = len(image_data)
                        return f"Screenshot saved to '{filename}' (window {captured_window_id}, {captured_format}, quality: {captured_quality}, size: {file_size} bytes)"

                    except Exception as e:
                        return f"Error saving screenshot to file '{filename}': {str(e)}"

                else:
                    # Return base64 data as before when no filename provided
                    data_size = len(base64_data)
                    return f"Screenshot captured successfully from window {captured_window_id} ({captured_format}, quality: {captured_quality}):\n{data_url[:100]}...\n\nBase64 data size: {data_size} characters"

            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to capture screenshot: {error_msg}"

            return "Unable to capture screenshot"

    def _setup_history_tools(self):
        """Setup history management tools"""

        # History Query Tool
        @self.mcp.tool()
        async def history_query(
            query: str,
            max_results: int = 200,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None
        ) -> str:
            """Search browser history

            Args:
                query: Substring to match in URL or title (exact substring match, not tokenized keywords)
                max_results: Maximum number of results (default: 200)
                start_time: Start time filter (ISO format, optional)
                end_time: End time filter (ISO format, optional)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.query",
                "data": {
                    "query": query,
                    "maxResults": max_results,
                    **({"startTime": start_time} if start_time else {}),
                    **({"endTime": end_time} if end_time else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error querying history: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                items = response["data"].get("items", [])
                total_count = response["data"].get("totalCount", len(items))

                if not items:
                    return f"No history items found for query: {query}"

                result = f"Found {total_count} history items for '{query}':\n"
                for item in items:
                    visit_time = item.get("lastVisitTime", "Unknown time")
                    visit_count = item.get("visitCount", 0)
                    result += f"- {item.get('title', 'No title')} - {item.get('url', 'No URL')} (visited {visit_count} times, last: {visit_time})\n"

                return result

            return f"Unable to query history for: {query}"

        # WebSocket Connection Status Tool (for debugging)
        @self.mcp.tool()
        async def debug_websocket_status() -> str:
            """Debug WebSocket connection status

            Returns information about the browser extension connection
            """
            if not hasattr(self.websocket_server, 'connected_clients'):
                return "WebSocket server doesn't track connected clients"

            try:
                client_count = len(getattr(self.websocket_server, 'connected_clients', []))
                return f"WebSocket status: {client_count} browser extension(s) connected"
            except Exception as e:
                return f"WebSocket status check failed: {e}"

        # Get Recent History Tool
        @self.mcp.tool()
        async def history_get_recent(count: int = 10) -> str:
            """Get recent browser history

            Args:
                count: Number of recent items to get (default: 10)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.recent",
                "data": {
                    "count": count
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            # Debug logging for troubleshooting
            import json
            print(f"🔍 DEBUG - Recent history WebSocket response: {json.dumps(response, indent=2)}")

            if "error" in response:
                return f"Error getting recent history: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                items = response["data"].get("items", [])

                if not items:
                    return "No recent history items found"

                result = f"Recent {len(items)} history items:\n"
                for item in items:
                    visit_time = item.get("lastVisitTime", "Unknown time")
                    result += f"- {item.get('title', 'No title')} - {item.get('url', 'No URL')} (last visit: {visit_time})\n"

                return result

            # More detailed error message for debugging
            return f"Unable to get recent history. Response type: {response.get('type')}, has_data: {'data' in response}, keys: {list(response.keys())}"

        # Delete History Item Tool
        @self.mcp.tool()
        async def history_delete_item(url: str) -> str:
            """Delete a specific history item

            Args:
                url: URL of the history item to delete
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.delete_item",
                "data": {
                    "url": url
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error deleting history item: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully deleted history item: {params.url}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to delete history item: {error_msg}"

            return f"Unable to delete history item: {params.url}"

    def _setup_bookmark_tools(self):
        """Setup bookmark management tools"""

        # List Bookmarks Tool
        @self.mcp.tool()
        async def bookmarks_list(folder_id: Optional[str] = None) -> str:
            """List browser bookmarks

            Folders are marked 📁 and bookmarks 🔖. Every line carries its own ID and its
            parent folder's ID — those IDs are what bookmarks_update, bookmarks_delete and
            the parent_id of bookmarks_create take, so this listing is how you find them.
            An empty folder returns "No bookmarks found".

            Args:
                folder_id: Optional folder ID to list bookmarks from

            Returns:
                Formatted string with bookmark information:
                "Bookmarks:
                📁 {folder_title} (ID: {folder_id}, Parent: {parent_id})
                🔖 {bookmark_title} - {bookmark_url} (ID: {bookmark_id}, Parent: {parent_id})"

                Not exposed to clients — see the description above.
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.list",
                "data": {
                    **({"folderId": folder_id} if folder_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error listing bookmarks: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                bookmarks = response["data"].get("bookmarks", [])

                if not bookmarks:
                    return "No bookmarks found"

                result = "Bookmarks:\n"
                for bookmark in bookmarks:
                    parent_info = f", Parent: {bookmark.get('parentId', 'None')}"
                    if bookmark.get("isFolder", False):
                        result += f"📁 {bookmark.get('title', 'Untitled Folder')} (ID: {bookmark.get('id')}{parent_info})\n"
                    else:
                        result += f"🔖 {bookmark.get('title', 'Untitled')} - {bookmark.get('url', 'No URL')} (ID: {bookmark.get('id')}{parent_info})\n"

                return result

            return "Unable to list bookmarks"

        # Search Bookmarks Tool
        @self.mcp.tool()
        async def bookmarks_search(query: str) -> str:
            """Search browser bookmarks by title or URL

            Matches bookmarks only — **folders are never returned**, so a folder cannot be
            found this way; use bookmarks_list to walk the tree instead. Each result carries
            its own ID and its parent folder's ID, which is what bookmarks_update and
            bookmarks_delete take. No matches returns "No bookmarks found".

            Args:
                query: Search query for bookmarks

            Returns:
                Formatted string with search results:
                "Found N bookmarks for 'query':
                🔖 {bookmark_title} - {bookmark_url} (ID: {bookmark_id}, Parent: {parent_id})"

                Not exposed to clients — see the description above.
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.search",
                "data": {
                    "query": query
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error searching bookmarks: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                bookmarks = response["data"].get("bookmarks", [])

                if not bookmarks:
                    return f"No bookmarks found for query: {query}"

                result = f"Found {len(bookmarks)} bookmarks for '{query}':\n"
                for bookmark in bookmarks:
                    if not bookmark.get("isFolder", False):
                        parent_info = f", Parent: {bookmark.get('parentId', 'None')}"
                        result += f"🔖 {bookmark.get('title', 'Untitled')} - {bookmark.get('url', 'No URL')} (ID: {bookmark.get('id')}{parent_info})\n"

                return result

            return f"Unable to search bookmarks for: {query}"

        # Create Bookmark Tool
        @self.mcp.tool()
        async def bookmarks_create(
            title: str,
            url: str,
            parent_id: Optional[str] = None
        ) -> str:
            """Create a new bookmark

            Args:
                title: Title of the bookmark
                url: URL of the bookmark
                parent_id: Optional parent folder ID
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.create",
                "data": {
                    "title": title,
                    "url": url,
                    **({"parentId": parent_id} if parent_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error creating bookmark: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                bookmark = response["data"].get("bookmark", {})
                return f"Created bookmark: {bookmark.get('title', title)} - {bookmark.get('url', url)} (ID: {bookmark.get('id')})"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to create bookmark: {error_msg}"

            return f"Unable to create bookmark: {title}"

        # Create Bookmark Folder Tool
        @self.mcp.tool()
        async def bookmarks_create_folder(
            title: str,
            parent_id: Optional[str] = None
        ) -> str:
            """Create a new bookmark folder

            Args:
                title: Title of the folder
                parent_id: Optional parent folder ID
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.createFolder",
                "data": {
                    "title": title,
                    **({"parentId": parent_id} if parent_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error creating folder: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                folder = response["data"].get("folder", {})
                return f"Created folder: {folder.get('title', title)} (ID: {folder.get('id')})"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to create folder: {error_msg}"

            return f"Unable to create folder: {title}"

        # Update Bookmark Tool
        @self.mcp.tool()
        async def bookmarks_update(
            bookmark_id: str,
            title: Optional[str] = None,
            url: Optional[str] = None
        ) -> str:
            """Update a bookmark or folder's title and/or URL

            Args:
                bookmark_id: ID of the bookmark or folder to update
                title: New title (optional)
                url: New URL (optional, only for bookmarks not folders)
            """
            if title is None and url is None:
                return "Error: At least one of title or url must be provided"

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.update",
                "data": {
                    "bookmarkId": bookmark_id,
                    **({"title": title} if title is not None else {}),
                    **({"url": url} if url is not None else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error updating bookmark: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                bookmark = response["data"].get("bookmark", {})
                return f"Updated bookmark: {bookmark.get('title', '')} (ID: {bookmark.get('id')})"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to update bookmark: {error_msg}"

            return f"Unable to update bookmark: {bookmark_id}"

        # Delete Bookmark Tool
        @self.mcp.tool()
        async def bookmarks_delete(bookmark_id: str) -> str:
            """Delete a bookmark

            Args:
                bookmark_id: ID of the bookmark to delete
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.delete",
                "data": {
                    "bookmarkId": bookmark_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error deleting bookmark: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully deleted bookmark {bookmark_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to delete bookmark: {error_msg}"

            return f"Unable to delete bookmark {bookmark_id}"

    def _setup_navigation_tools(self):
        """Setup navigation tools"""

        # Navigate Back Tool
        class NavigationBackParams(BaseModel):
            """Parameters for navigating back"""
            tab_id: int = Field(description="ID of the tab to navigate back in")

        @self.mcp.tool()
        async def navigation_back(params: NavigationBackParams) -> str:
            """Navigate back in browser history for a tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.back",
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error navigating back: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully navigated back in tab {params.tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to navigate back: {error_msg}"

            return f"Unable to navigate back in tab {params.tab_id}"

        # Navigate Forward Tool
        class NavigationForwardParams(BaseModel):
            """Parameters for navigating forward"""
            tab_id: int = Field(description="ID of the tab to navigate forward in")

        @self.mcp.tool()
        async def navigation_forward(params: NavigationForwardParams) -> str:
            """Navigate forward in browser history for a tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.forward",
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error navigating forward: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully navigated forward in tab {params.tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to navigate forward: {error_msg}"

            return f"Unable to navigate forward in tab {params.tab_id}"

        # Reload Page Tool
        @self.mcp.tool()
        async def navigation_reload(tab_id: int, bypass_cache: bool = False) -> str:
            """Reload a page in a tab

            Args:
                tab_id: ID of the tab to reload
                bypass_cache: Whether to bypass cache when reloading (default: False)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.reload",
                "data": {
                    "tabId": tab_id,
                    "bypassCache": bypass_cache
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error reloading page: {response['error']}"

            if response.get("type") == "response":
                cache_text = " (bypassing cache)" if bypass_cache else ""
                return f"Successfully reloaded tab {tab_id}{cache_text}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to reload page: {error_msg}"

            return f"Unable to reload tab {tab_id}"

        # Go to URL Tool
        @self.mcp.tool()
        async def navigation_go_to_url(tab_id: int, url: str) -> str:
            """Navigate to a specific URL in a tab

            Args:
                tab_id: ID of the tab to navigate
                url: URL to navigate to
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.go_to_url",
                "data": {
                    "tabId": tab_id,
                    "url": url
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error navigating to URL: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully navigated tab {tab_id} to {url}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to navigate to URL: {error_msg}"

            return f"Unable to navigate tab {tab_id} to {url}"

    def _setup_content_tools(self):
        """Setup content access tools"""

        # Get Page Text Tool
        @self.mcp.tool()
        async def content_get_text(tab_id: int, max_length: Optional[int] = None) -> str:
            """Get text content from a tab's page

            Args:
                tab_id: ID of the tab to get content from
                max_length: Optional maximum length of text to return (default: unlimited)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "content.get_text",
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error getting page text: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                text = response["data"].get("text", "")
                url = response["data"].get("url", "Unknown URL")
                title = response["data"].get("title", "Unknown Title")

                if not text:
                    return f"No text content found in tab {tab_id} ({title})"

                # Apply length limit if specified
                if max_length is not None and len(text) > max_length:
                    truncated_text = text[:max_length]
                    return f"Text content from {title} ({url}):\n\n{truncated_text}..."
                else:
                    return f"Text content from {title} ({url}):\n\n{text}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to get page text: {error_msg}"

            return f"Unable to get text content from tab {tab_id}"

        # Get Page HTML Tool
        @self.mcp.tool()
        async def content_get_html(tab_id: int) -> str:
            """Get HTML content from a tab's page

            Args:
                tab_id: ID of the tab to get HTML content from
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "content.get_html",
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error getting page HTML: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                html = response["data"].get("html", "")
                url = response["data"].get("url", "Unknown URL")
                title = response["data"].get("title", "Unknown Title")

                if not html:
                    return f"No HTML content found in tab {tab_id} ({title})"

                return f"HTML content from {title} ({url}):\n\n{html[:2000]}{'...' if len(html) > 2000 else ''}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to get page HTML: {error_msg}"

            return f"Unable to get HTML content from tab {tab_id}"

        # Execute Script Tool
        @self.mcp.tool()
        async def content_execute_script(tab_id: int, code: str) -> str:
            """Execute JavaScript code in a tab

            Args:
                tab_id: ID of the tab to execute script in
                code: JavaScript code to execute
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "content.execute_script",
                "data": {
                    "tabId": tab_id,
                    "script": code
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return f"Error executing script: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                result = response["data"].get("result")
                url = response["data"].get("url", "Unknown URL")

                if result is None:
                    return f"Script executed successfully in tab {tab_id} ({url}) - no return value"

                return f"Script result from tab {tab_id} ({url}):\n{result}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to execute script: {error_msg}"

            return f"Unable to execute script in tab {tab_id}"

        # Execute Predefined Script Tool
        @self.mcp.tool()
        async def content_execute_predefined(
            tab_id: int,
            script_name: str,
            script_args: str = ""
        ) -> str:
            """Execute a predefined external script and run its JavaScript output in a tab

            Args:
                tab_id: ID of the tab to execute script in
                script_name: Name of the external script to run
                script_args: JSON array of strings to pass to the external script (e.g., '["arg1", "arg2"]')
                            or empty string for no arguments
            """
            # Every rejection below is logged at warning level.
            #
            # This is the code-execution surface an MCP client can reach, so a
            # refusal is worth a line whether it came from a typo or from an
            # attempt to escape the scripts directory - the two are
            # indistinguishable here, and only the log preserves the attempt.

            # Get the scripts directory from environment variable
            scripts_dir = os.environ.get('FOXMCP_EXT_SCRIPTS')
            if not scripts_dir:
                logger.warning(
                    f"Predefined script '{script_name}' refused: FOXMCP_EXT_SCRIPTS is not set"
                )
                return "Error: FOXMCP_EXT_SCRIPTS environment variable not set"

            # Validate script name to prevent path traversal attacks
            if not script_name or '..' in script_name or '/' in script_name or '\\' in script_name:
                logger.warning(
                    f"Predefined script refused: name {script_name!r} contains a path separator or '..'"
                )
                return f"Error: Invalid script name '{script_name}'. Script names cannot contain path separators or '..' sequences"

            # Additional validation: only allow alphanumeric, underscore, dash, and dot
            import re
            if not re.match(r'^[a-zA-Z0-9._-]+$', script_name):
                logger.warning(
                    f"Predefined script refused: name {script_name!r} has characters outside [a-zA-Z0-9._-]"
                )
                return f"Error: Invalid script name '{script_name}'. Only alphanumeric characters, underscore, dash, and dot are allowed"

            # Resolve absolute paths to prevent symlink attacks
            scripts_dir = os.path.abspath(scripts_dir)
            script_path = os.path.abspath(os.path.join(scripts_dir, script_name))

            # Ensure the resolved script path is still within the scripts directory
            if not script_path.startswith(scripts_dir + os.sep) and script_path != scripts_dir:
                logger.warning(
                    f"Predefined script refused: {script_name!r} resolves to {script_path!r}, "
                    f"outside {scripts_dir!r}"
                )
                return f"Error: Script path '{script_name}' escapes the allowed directory"

            if not os.path.exists(script_path):
                logger.warning(f"Predefined script refused: {script_name!r} not found in {scripts_dir!r}")
                return f"Error: Script '{script_name}' not found in {scripts_dir}"

            if not os.access(script_path, os.X_OK):
                logger.warning(f"Predefined script refused: {script_name!r} is not executable")
                return f"Error: Script '{script_name}' is not executable"

            try:
                # Parse JSON arguments - handle both empty string and JSON arrays
                try:
                    if script_args.strip() == "":
                        # Empty string means no arguments
                        args_list = []
                    else:
                        # Parse as JSON array
                        args_list = json.loads(script_args)
                        if not isinstance(args_list, list):
                            logger.warning(
                                f"Predefined script {script_name!r} refused: script_args is "
                                f"{type(args_list).__name__}, not a list"
                            )
                            return f"Error: script_args must be a JSON array of strings or empty string, got: {type(args_list).__name__}"

                        # Validate all arguments are strings
                        for i, arg in enumerate(args_list):
                            if not isinstance(arg, str):
                                logger.warning(
                                    f"Predefined script {script_name!r} refused: argument {i} is "
                                    f"{type(arg).__name__}, not a string"
                                )
                                return f"Error: All arguments must be strings. Argument {i} is {type(arg).__name__}: {arg}"

                except json.JSONDecodeError as e:
                    logger.warning(f"Predefined script {script_name!r} refused: script_args is not valid JSON - {e}")
                    return f"Error: Invalid JSON in script_args: {e}"

                # Execute the external script with arguments
                logger.info(
                    f"Running predefined script {script_name!r} in tab {tab_id} "
                    f"with {format_script_args_for_log(args_list)}"
                )
                started_at = time.monotonic()
                result = subprocess.run(
                    [script_path] + args_list,
                    capture_output=True,
                    text=True,
                    timeout=30  # 30 second timeout
                )
                elapsed = time.monotonic() - started_at

                if result.returncode != 0:
                    logger.warning(
                        f"Predefined script {script_name!r} exited {result.returncode} "
                        f"after {elapsed:.1f}s: {result.stderr.strip()!r}"
                    )
                    return f"Error: Script '{script_name}' failed with exit code {result.returncode}. stderr: {result.stderr}"

                # The script output should be JavaScript code
                javascript_code = result.stdout.strip()
                if not javascript_code:
                    logger.warning(f"Predefined script {script_name!r} produced no output after {elapsed:.1f}s")
                    return f"Error: Script '{script_name}' produced no output"

                # Log the size, never the JavaScript itself - a generated
                # DOM-walking script runs to tens of kilobytes and would bury
                # every other line in the log.
                logger.info(
                    f"Predefined script {script_name!r} generated {len(javascript_code)} bytes "
                    f"of JavaScript in {elapsed:.1f}s; injecting into tab {tab_id}"
                )

                # Now execute the generated JavaScript in the tab
                request = {
                    "id": str(uuid.uuid4()),
                    "type": "request",
                    "action": "content.execute_script",
                    "data": {
                        "tabId": tab_id,
                        "script": javascript_code
                    },
                    "timestamp": datetime.now().isoformat()
                }

                response = await self.websocket_server.send_request_and_wait(request)

                if "error" in response:
                    logger.warning(
                        f"Predefined script {script_name!r} failed in tab {tab_id}: {response['error']}"
                    )
                    return f"Error executing generated script: {response['error']}"

                if response.get("type") == "response" and "data" in response:
                    result_data = response["data"].get("result")
                    url = response["data"].get("url", "Unknown URL")

                    # The URL is the point of this line: it says which page the
                    # script actually ran against, which the tab id alone does
                    # not - the tab may have navigated since the caller chose it.
                    logger.info(f"Predefined script {script_name!r} completed in tab {tab_id} ({url})")

                    if result_data is None:
                        return f"Predefined script '{script_name}' executed successfully in tab {tab_id} ({url}) - no return value"

                    return f"Predefined script '{script_name}' result from tab {tab_id} ({url}):\n{result_data}"
                elif response.get("type") == "error":
                    error_msg = response.get("data", {}).get("message", "Unknown error")
                    logger.warning(
                        f"Predefined script {script_name!r} failed in tab {tab_id}: {error_msg}"
                    )
                    return f"Failed to execute generated script: {error_msg}"

                return f"Unable to execute generated script in tab {tab_id}"

            except subprocess.TimeoutExpired:
                logger.warning(f"Predefined script {script_name!r} timed out after 30 seconds and was killed")
                return f"Error: Script '{script_name}' timed out after 30 seconds"
            except subprocess.SubprocessError as e:
                logger.warning(f"Predefined script {script_name!r} could not be run: {e}")
                return f"Error executing script '{script_name}': {e}"
            except Exception as e:
                logger.exception(f"Predefined script {script_name!r} raised an unexpected error")
                return f"Unexpected error running script '{script_name}': {e}"

    def _setup_request_monitoring_tools(self):
        """Setup web request monitoring tools"""

        @self.mcp.tool()
        async def requests_start_monitoring(
            url_patterns: List[str],
            options: Optional[Dict[str, Any]] = None,
            tab_id: Optional[int] = None
        ) -> str:
            """
            Start monitoring web requests

            Returns JSON containing a **monitor_id**. Keep it — requests_list_captured,
            requests_get_content and requests_stop_monitoring all take it, so losing it
            leaves the monitor running with no way to read or stop it.

            Args:
                url_patterns: List of URL patterns to monitor (e.g., ["https://api.example.com/*", "*/api/*"])
                options: Optional configuration for monitoring:
                    - capture_request_bodies: bool (default: True)
                    - capture_response_bodies: bool (default: True)
                    - max_body_size: int (default: 50000)
                    - content_types_to_capture: List[str] (default: ["application/json", "text/plain"])
                    - sensitive_headers: List[str] (default: ["Authorization", "Cookie"])
                tab_id: Optional tab ID to monitor (if not provided, monitors all tabs)

            Returns:
                JSON string with monitor_id and status information
            """
            if not url_patterns:
                return json.dumps({"error": "url_patterns is required"})

            # Set default options
            default_options = {
                "capture_request_bodies": True,
                "capture_response_bodies": True,
                "max_body_size": 50000,
                "content_types_to_capture": ["application/json", "text/plain"],
                "sensitive_headers": ["Authorization", "Cookie"]
            }

            if options:
                default_options.update(options)

            request_data = {
                "url_patterns": url_patterns,
                "options": default_options
            }

            if tab_id is not None:
                request_data["tab_id"] = tab_id

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "requests.start_monitoring",
                "data": request_data,
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return json.dumps({"error": f"Failed to start monitoring: {response['error']}"})

            if response.get("type") == "response" and "data" in response:
                return json.dumps(response["data"])
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return json.dumps({"error": f"Failed to start monitoring: {error_msg}"})

            return json.dumps({"error": "Unable to start monitoring"})

        @self.mcp.tool()
        async def requests_stop_monitoring(
            monitor_id: str,
            drain_timeout: int = 5
        ) -> str:
            """
            Stop monitoring web requests with graceful drainage

            Args:
                monitor_id: ID of the monitoring session to stop
                drain_timeout: Seconds to wait for in-flight requests (default: 5)

            Returns:
                JSON string with stop status and statistics
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "requests.stop_monitoring",
                "data": {
                    "monitor_id": monitor_id,
                    "drain_timeout": drain_timeout
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return json.dumps({"error": f"Failed to stop monitoring: {response['error']}"})

            if response.get("type") == "response" and "data" in response:
                return json.dumps(response["data"])
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return json.dumps({"error": f"Failed to stop monitoring: {error_msg}"})

            return json.dumps({"error": "Unable to stop monitoring"})

        @self.mcp.tool()
        async def requests_list_captured(monitor_id: str) -> str:
            """
            List all captured request summaries from a monitoring session

            Args:
                monitor_id: ID of the monitoring session

            Returns:
                JSON string with captured request summaries
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "requests.list_captured",
                "data": {
                    "monitor_id": monitor_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return json.dumps({"error": f"Failed to list captured requests: {response['error']}"})

            if response.get("type") == "response" and "data" in response:
                return json.dumps(response["data"])
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return json.dumps({"error": f"Failed to list captured requests: {error_msg}"})

            return json.dumps({"error": "Unable to list captured requests"})

        @self.mcp.tool()
        async def requests_get_content(
            monitor_id: str,
            request_id: str,
            include_binary: bool = False,
            save_request_body_to: Optional[str] = None,
            save_response_body_to: Optional[str] = None
        ) -> str:
            """
            Get full request/response content for a specific request

            Args:
                monitor_id: ID of the monitoring session
                request_id: ID of the specific request
                include_binary: Whether to return binary content as base64 (default: False)
                save_request_body_to: Optional file path to save request body
                save_response_body_to: Optional file path to save response body

            Returns:
                JSON string with full request/response content
            """
            request_data = {
                "monitor_id": monitor_id,
                "request_id": request_id,
                "include_binary": include_binary
            }

            if save_request_body_to:
                request_data["save_request_body_to"] = save_request_body_to
            if save_response_body_to:
                request_data["save_response_body_to"] = save_response_body_to

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "requests.get_content",
                "data": request_data,
                "timestamp": datetime.now().isoformat()
            }

            response = await self.websocket_server.send_request_and_wait(request)

            if "error" in response:
                return json.dumps({"error": f"Failed to get request content: {response['error']}"})

            if response.get("type") == "response" and "data" in response:
                return json.dumps(response["data"])
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return json.dumps({"error": f"Failed to get request content: {error_msg}"})

            return json.dumps({"error": "Unable to get request content"})

    def get_mcp_app(self):
        """Get the FastMCP application instance"""
        return self.mcp